#!/usr/bin/env python3
"""
Agent Pipeline Dashboard Server
HTTP + SSE + Workflow Execution

Architecture: When a user submits a workflow task via the UI, the server
executes it phase-by-phase: resetting state, advancing agent statuses through
pending → running → done with progressive logs, and broadcasting real-time
SSE events. Agent output files are written to the appropriate workflow's
output/ directory so the render scripts can pick them up.
"""
import json
import time
import threading
import queue
import os
import sys
import uuid
import random
import subprocess
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path
from typing import List, Dict, Any

DASHBOARD_DIR = Path(__file__).parent.resolve()
STATE_FILE = DASHBOARD_DIR / "state.json"
PIPELINE_FILE = DASHBOARD_DIR / "pipeline.json"
ROOT_DIR = DASHBOARD_DIR.parent

event_queues: List[queue.Queue] = []


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class DashboardHandler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/events":
            self._handle_sse(); return
        if path == "/api/state":
            self._send_json(self._load_state()); return
        if path == "/api/pipeline":
            self._send_json(self._load_pipeline()); return
        if path == "/api/reset":
            self._reset_state()
            self._broadcast({"type": "reset", "data": self._load_state()})
            self._send_json({"ok": True}); return
        if path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self):
        path = self.path.split("?")[0]

        if path == "/api/agent/update":
            self._handle_agent_update(); return

        if path == "/api/workflow/execute":
            self._handle_execute(); return

        if path == "/api/simulate":
            t = threading.Thread(target=self._simulate_run, daemon=True)
            t.start()
            self._send_json({"ok": True, "message": "模拟运行已启动"})
            return

        self.send_error(405)

    # ── SSE ──────────────────────────────────────────────

    def _handle_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        q = queue.Queue()
        event_queues.append(q)
        try:
            while True:
                try:
                    msg = q.get(timeout=30)
                    self.wfile.write(
                        f"data: {json.dumps(msg, ensure_ascii=False)}\n\n".encode()
                    )
                    self.wfile.flush()
                except queue.Empty:
                    self.wfile.write(": heartbeat\n\n".encode())
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            event_queues.remove(q)

    # ── Helpers ──────────────────────────────────────────

    def _send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _load_state(self):
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))

    def _load_pipeline(self):
        return json.loads(PIPELINE_FILE.read_text(encoding="utf-8"))

    def _save_state(self, state):
        STATE_FILE.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _reset_state(self):
        initial_state = {
            "active_workflow": None,
            "started_at": None,
            "repo-due-diligence": self._make_workflow_state("repo-due-diligence"),
            "dev-workflow": self._make_workflow_state("dev-workflow"),
            "universal-search": self._make_workflow_state("universal-search"),
            "overall_progress": 0,
            "events": [],
        }
        self._save_state(initial_state)

    def _make_workflow_state(self, wf_name: str) -> dict:
        pipeline = self._load_pipeline()
        wf = pipeline["workflows"].get(wf_name, {})
        phases = {}
        agents = {}
        for p in wf.get("phases", []):
            phases[p["id"]] = {"status": "pending"}
            for a in p.get("agents", []):
                agents[a["id"]] = {
                    "status": "pending",
                    "progress": 0,
                    "started_at": None,
                    "finished_at": None,
                    "model": a.get("model", ""),
                    "log": [],
                }
                if "children" in a:
                    agents[a["id"]]["children_total"] = a["children"]
                    agents[a["id"]]["children_done"] = 0
        return {"status": "idle", "phases": phases, "agents": agents}

    def _broadcast(self, msg):
        dead = []
        for q in event_queues:
            try:
                q.put_nowait(msg)
            except queue.Full:
                dead.append(q)
        for q in dead:
            event_queues.remove(q)

    def _now_ts(self):
        return time.strftime("%H:%M:%S")

    def _now_full(self):
        return time.strftime("%Y-%m-%d %H:%M:%S")

    # ── Agent update ─────────────────────────────────────

    def _update_agent_state(
        self,
        wf_name: str,
        agent_id: str,
        status: str,
        progress: int = 0,
        log_msg: str = "",
        children_done: int = None,
    ):
        state = self._load_state()
        agent = state[wf_name]["agents"].get(agent_id)
        if not agent:
            return
        now = self._now_ts()
        agent["status"] = status
        agent["progress"] = progress
        if status == "running" and agent.get("started_at") is None:
            agent["started_at"] = now
        if status in ("done", "failed"):
            agent["finished_at"] = now
            agent["progress"] = 100
        if children_done is not None:
            agent["children_done"] = children_done
        if log_msg:
            agent["log"].append(f"[{now}] {log_msg}")

        pipeline = self._load_pipeline()
        wf_def = pipeline["workflows"][wf_name]
        for phase in wf_def["phases"]:
            aids = [a["id"] for a in phase["agents"]]
            astates = [state[wf_name]["agents"][aid]["status"] for aid in aids]
            if all(s == "done" for s in astates):
                state[wf_name]["phases"][phase["id"]]["status"] = "done"
            elif any(s == "running" for s in astates):
                state[wf_name]["phases"][phase["id"]]["status"] = "running"
            elif any(s == "failed" for s in astates):
                state[wf_name]["phases"][phase["id"]]["status"] = "failed"

        all_done = all(
            state[wf_name]["agents"][aid]["status"] == "done"
            for aid in state[wf_name]["agents"]
        )
        if all_done:
            state[wf_name]["status"] = "done"
        elif any(
            state[wf_name]["agents"][aid]["status"] == "running"
            for aid in state[wf_name]["agents"]
        ):
            state[wf_name]["status"] = "running"

        self._save_state(state)
        self._broadcast({"type": "state_update", "data": state})

    # ── Workflow execution ───────────────────────────────

    def _handle_execute(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"ok": False, "error": "Invalid JSON"}, 400)
            return
        workflow = data.get("workflow")
        user_input = data.get("input", "")
        if workflow not in ("repo-due-diligence", "dev-workflow", "universal-search"):
            self._send_json({"ok": False, "error": f"Unknown workflow: {workflow}"}, 400)
            return

        task_id = f"task-{uuid.uuid4().hex[:10]}"
        self._send_json({"ok": True, "task_id": task_id})

        t = threading.Thread(
            target=self._run_workflow, args=(workflow, user_input, task_id), daemon=True
        )
        t.start()

    def _run_workflow(self, wf_name: str, user_input: str, task_id: str):
        now = self._now_ts()

        # Reset & init
        self._reset_state()
        state = self._load_state()
        state["active_workflow"] = wf_name
        state["started_at"] = self._now_full()
        state[wf_name]["status"] = "running"
        self._save_state(state)

        self._broadcast({
            "type": "execution_start",
            "workflow": wf_name,
            "input": user_input,
            "task_id": task_id,
            "msg": f"[{now}] 工作流启动: {wf_name} | 输入: {user_input[:80]}",
        })

        pipeline = self._load_pipeline()
        wf_def = pipeline["workflows"].get(wf_name)
        if not wf_def:
            return

        # Ensure output dir
        out_dir = ROOT_DIR / wf_name / "output"
        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            phases = wf_def["phases"]
            for pi, phase in enumerate(phases):
                pid = phase["id"]
                pname = phase["name"]
                self._broadcast({
                    "type": "execution_log",
                    "msg": f"[{self._now_ts()}] 进入 {pname}",
                })
                self._broadcast({
                    "type": "phase_change",
                    "phase": pname,
                })

                # Set phase to running
                state = self._load_state()
                state[wf_name]["phases"][pid]["status"] = "running"
                self._save_state(state)
                self._broadcast({"type": "state_update", "data": state})

                agents = phase["agents"]
                agent_outs = {}  # collect outputs for this phase

                # Run agents (parallel in same phase = run sequentially but fast)
                for agent_def in agents:
                    aid = agent_def["id"]
                    aname = agent_def.get("name", aid)

                    self._log_and_update(wf_name, aid, aname, "开始执行")

                    # Simulate meaningful progress
                    total_steps = random.randint(8, 15)
                    for step in range(1, total_steps + 1):
                        progress = int(step / total_steps * 95)
                        time.sleep(random.uniform(0.08, 0.25))
                        msgs = self._progress_msgs(wf_name, aid, step, total_steps)
                        if msgs:
                            for m in msgs:
                                self._log_and_update(
                                    wf_name, aid, aname, m, progress
                                )

                        # Update children progress for fan-out agents
                        if "children" in agent_def:
                            children_total = agent_def["children"]
                            children_done = min(
                                int(children_total * progress / 100) + 1,
                                children_total,
                            )
                            state = self._load_state()
                            agent = state[wf_name]["agents"][aid]
                            agent["progress"] = progress
                            agent["children_done"] = children_done
                            self._save_state(state)
                            self._broadcast({"type": "state_update", "data": state})

                    # Generate mock output for this agent
                    output_content = self._gen_agent_output(
                        wf_name, aid, user_input, task_id
                    )
                    if output_content:
                        output_file = agent_def.get("output", f"{aid}.json")
                        out_path = out_dir / output_file
                        out_path.write_text(output_content, encoding="utf-8")
                        agent_outs[aid] = str(out_path)

                    self._log_and_update(
                        wf_name, aid, aname,
                        f"执行完成 → 产出 {agent_def.get('output', 'N/A')}",
                        100, "done"
                    )

                # Phase done
                state = self._load_state()
                state[wf_name]["phases"][pid]["status"] = "done"
                self._save_state(state)
                self._broadcast({
                    "type": "execution_log",
                    "msg": f"[{self._now_ts()}] {pname} 完成",
                })
                self._broadcast({"type": "state_update", "data": state})

            # ── Render final report ──
            final_path = self._render_final_report(wf_name, user_input, task_id, out_dir)
            self._broadcast({
                "type": "execution_log",
                "msg": f"[{self._now_ts()}] 渲染最终报告: {final_path}",
            })

            # All done
            state = self._load_state()
            state[wf_name]["status"] = "done"
            self._save_state(state)
            self._broadcast({"type": "state_update", "data": state})

            finish_time = self._now_ts()
            self._broadcast({
                "type": "execution_complete",
                "task_id": task_id,
                "time": finish_time,
                "msg": f"[{finish_time}] 工作流执行完成: {wf_name}",
                "output_file": final_path,
                "output_name": Path(final_path).name if final_path else "",
            })

        except Exception as e:
            self._broadcast({
                "type": "execution_log",
                "msg": f"[{self._now_ts()}] ERROR: {str(e)}",
            })
            state = self._load_state()
            state[wf_name]["status"] = "failed"
            self._save_state(state)
            self._broadcast({"type": "state_update", "data": state})
            self._broadcast({
                "type": "execution_complete",
                "task_id": task_id,
                "time": self._now_ts(),
                "msg": f"[{self._now_ts()}] 执行失败: {str(e)}",
            })

    def _log_and_update(self, wf_name, aid, aname, msg, progress=0, status="running"):
        ts = self._now_ts()
        self._broadcast({
            "type": "execution_log",
            "msg": f"[{ts}] [{aname}] {msg}",
        })
        state = self._load_state()
        agent = state[wf_name]["agents"][aid]
        agent["status"] = status
        agent["progress"] = progress
        if status == "running" and agent.get("started_at") is None:
            agent["started_at"] = ts
        if status == "done":
            agent["finished_at"] = ts
            agent["progress"] = 100
        agent["log"].append(f"[{ts}] {msg}")
        self._save_state(state)
        self._broadcast({"type": "state_update", "data": state})

    def _progress_msgs(self, wf_name, aid, step, total):
        """Generate realistic progress messages for different agents."""
        ui_messages = {
            "search": [
                "提取查询特征...", "构建搜索策略...",
                "多源搜索中...", "解析搜索结果...", "去重处理中...",
                "整理搜索结果...",
            ],
            "scorer": [
                "接收分配条目...", "检查信息相关性...",
                "评估权威性...", "评估时效性...", "评估信息密度...",
                "计算综合权重...", "判定保留/丢弃...",
            ],
            "judgment": [
                "收集所有 Scorer 输出...", "去重检查中...",
                "一致性校验中...", "全局权重排序...", "生成筛选报告...",
            ],
            "doc-writer": [
                "读取筛选结果...", "提取关键词...",
                "按权重排序...", "生成分布统计...", "格式化 Markdown...",
            ],
            "summary": [
                "阅读调研文档...", "提炼关键发现...",
                "分析趋势...", "撰写执行摘要...", "生成行动建议...",
            ],
            "recon": [
                "读取 README...", "分析 Issue 列表...",
                "提取项目信息...", "识别关键问题...", "生成侦查报告...",
            ],
            "code-review": [
                "选取核心文件...", "分发子 Review 任务...",
                "收集子模型结果...", "综合评分...", "生成代码报告...",
            ],
            "health-metrics": [
                "获取仓库元数据...", "分析 commit 趋势...",
                "计算社区指标...", "评估健康度...", "生成健康报告...",
            ],
            "usage-guide": [
                "提取安装步骤...", "解析配置文件...",
                "整理常用命令...", "收集使用场景...", "生成使用指南...",
            ],
            "risk-analyst": [
                "加载上游报告...", "评估技术债...", "评估维护风险...",
                "评估社区风险...", "评估 License...", "生成最终结论...",
            ],
            "requirement": [
                "读取需求文档...", "拆解功能点...", "标注优先级...",
                "分析依赖关系...", "生成需求清单...",
            ],
            "architecture": [
                "分析功能清单...", "设计模块架构...",
                "定义 API 接口...", "设计数据模型...", "输出架构文档...",
            ],
            "coding": [
                "读取架构设计...", "生成 Controller...",
                "生成 Service 层...", "生成 Mapper...",
                "生成配置类...", "自检代码质量...",
            ],
            "whitebox": [
                "静态代码分析...", "逻辑路径审查...",
                "安全漏洞扫描...", "边界值测试...", "生成白盒报告...",
            ],
            "blackbox": [
                "设计测试用例...", "功能测试...",
                "集成场景测试...", "安全测试...", "生成黑盒报告...",
            ],
            "review": [
                "加载全流程产物...", "需求匹配度评分...",
                "代码质量评分...", "综合评分...", "生成改进建议...",
            ],
        }

        if step == 1:
            return ["初始化中..."]
        if step >= total:
            return []

        # Pick relevant messages based on agent type
        for prefix, msgs in ui_messages.items():
            if aid.startswith(prefix) or aid == prefix:
                idx = (step - 2) % len(msgs) if len(msgs) > 0 else 0
                if step - 2 < len(msgs):
                    return [msgs[step - 2]]
                return []

        return ["处理中..."]

    def _gen_agent_output(self, wf_name, aid, user_input, task_id):
        """Generate rich structured output for an agent."""
        now = self._now_full()
        today = datetime.now().strftime("%Y-%m-%d")

        if wf_name == "universal-search":
            if aid == "search":
                keywords = [w.strip() for w in user_input.split()[:5]]
                total = random.randint(10, 16)
                return json.dumps({
                    "query": user_input,
                    "task_id": task_id,
                    "extracted_features": {
                        "keywords": keywords if keywords else [user_input],
                        "domain": "技术",
                        "timeliness": "近一年",
                        "depth": "中等",
                    },
                    "total_results": total,
                    "results": [
                        {
                            "id": i,
                            "title": f"「{user_input}」相关资料 {i}",
                            "summary": f"与「{user_input}」高度相关的搜索结果，涵盖核心技术要点和实践经验，信息密度适中，来源可靠。",
                            "url": f"https://result.example.com/{i}",
                            "source_type": "技术博客" if i % 3 != 0 else "官方文档",
                            "publish_date": f"2025-{random.randint(1,6):02d}-{random.randint(1,28):02d}",
                            "author": f"作者-{i}",
                        }
                        for i in range(1, total + 1)
                    ],
                }, ensure_ascii=False, indent=2)

            if aid.startswith("scorer-"):
                n = aid.split("-")[1]
                retained = random.randint(1, 2)
                return json.dumps({
                    "scorer_id": aid,
                    "query": user_input,
                    "results": [
                        {
                            "id": int(n) * 2 - 1 + j,
                            "title": f"「{user_input}」搜索结果 {int(n) * 2 - 1 + j}",
                            "url": f"https://result.example.com/{int(n) * 2 - 1 + j}",
                            "source_type": "技术博客",
                            "publish_date": f"2025-{random.randint(1,6):02d}-{random.randint(1,28):02d}",
                            "scores": {
                                "relevance": random.randint(6, 10),
                                "authority": random.randint(5, 10),
                                "timeliness": random.randint(6, 10),
                                "density": random.randint(5, 10),
                            },
                            "weight": round(random.uniform(0.4, 0.95), 2),
                            "verdict": "保留",
                            "reason": f"与查询「{user_input}」相关，信息有价值",
                        }
                        for j in range(retained)
                    ],
                    "retained_count": retained,
                    "discarded_count": 2 - retained,
                }, ensure_ascii=False, indent=2)

            if aid == "judgment":
                return json.dumps({
                    "query": user_input,
                    "scorer_stats": {"total_scorers": 10, "total_assigned": 15, "total_retained": 12, "total_discarded_by_scorers": 3, "duplicates_merged": 2},
                    "filtered_count": 10,
                    "discarded_count": 2,
                    "discard_reasons": [{"id": 15, "reason": "内容重复"}, {"id": 13, "reason": "信息量不足"}],
                    "results": [
                        {
                            "id": i,
                            "title": f"「{user_input}」精选结果 {i}",
                            "url": f"https://result.example.com/{i}",
                            "source_type": "技术博客" if i % 3 != 0 else "官方文档",
                            "publish_date": f"2025-{random.randint(1,6):02d}",
                            "author": f"作者-{i}",
                            "scores": {"relevance": 9-i//5, "authority": 8-i//6, "timeliness": 9, "density": 8-i//5},
                            "weight": round(0.95 - i * 0.03, 2),
                            "scored_by": f"scorer-{min(i, 10)}",
                            "verdict": "保留",
                            "reason": f"与查询「{user_input}」高度相关，信息密度高",
                        }
                        for i in range(1, 11)
                    ],
                    "sort_order": "按综合权重从高到低排序",
                    "judgment_summary": f"收集10个Scorer输出，经去重和一致性检查，最终保留10条与「{user_input}」相关的高价值结果，权重范围0.65-0.92。",
                }, ensure_ascii=False, indent=2)

            if aid == "doc-writer":
                # Generate meaningful markdown for the render script
                lines = [
                    f"# 信息研究报告：{user_input}",
                    "",
                    f"**生成时间**：{today}",
                    f"**搜索特征**：{user_input}",
                    f"**结果数量**：10 条（已按权重排序）",
                    "",
                    "---",
                    "",
                    "## 搜索概述",
                    "",
                    f"本次调研围绕「{user_input}」展开，覆盖多个主流技术平台。通过相关性、权威性、时效性、信息密度四维加权评估，筛选出高质量信息。",
                    "",
                    "---",
                    "",
                    "## 调研结果",
                    "",
                    "### 高价值信息（weight ≥ 0.7）",
                    "",
                ]
                for i in range(1, 7):
                    w = round(0.95 - i * 0.03, 2)
                    lines += [
                        f"#### {i}. 「{user_input}」精选结果 {i}",
                        "",
                        f"| 维度 | 得分 |",
                        f"|------|------|",
                        f"| **综合权重** | {w:.2f} |",
                        f"| 相关性 | {9-i//8}/10 |",
                        f"| 权威性 | {8-i//6}/10 |",
                        f"| 时效性 | 9/10 |",
                        f"| 信息密度 | {8-i//5}/10 |",
                        "",
                        f"- **关键词**：`{user_input}` `结果{i}`",
                        f"- **来源**：技术博客",
                        f"- **源地址**：https://result.example.com/{i}",
                        "",
                        f"**摘要**：与「{user_input}」相关的高价值信息，包含核心技术要点和实践指导。",
                        "",
                    ]
                lines += [
                    "### 中等价值信息（0.4 ≤ weight < 0.7）",
                    "",
                ]
                for i in range(7, 11):
                    w = round(0.95 - i * 0.03, 2)
                    lines += [
                        f"#### {i}. 「{user_input}」精选结果 {i}",
                        f"- **权重**：{w:.2f} | **来源**：技术博客",
                        f"- **源地址**：https://result.example.com/{i}",
                        f"**摘要**：补充信息，有一定参考价值。",
                        "",
                    ]

                lines += [
                    "---",
                    "",
                    "## 信息分布统计",
                    "",
                    "| 来源类型 | 数量 |",
                    "|----------|------|",
                    "| 技术博客 | 7 |",
                    "| 官方文档 | 3 |",
                    "",
                    "---",
                    "",
                    "## 信息来源清单",
                    "",
                ]
                for i in range(1, 11):
                    lines.append(f"- [{user_input} 结果{i}](https://result.example.com/{i})")
                lines.append("")
                lines.append(f"*报告生成时间：{today} | 共收录 10 条有效结果*")

                return "\n".join(lines)

            if aid == "summary":
                return json.dumps({
                    "query": user_input,
                    "date": today,
                    "key_findings": [
                        {"finding": f"关于「{user_input}」的核心发现：主流技术方向明确", "source_id": 1, "confidence": "高"},
                        {"finding": f"「{user_input}」领域的最佳实践已形成共识", "source_id": 3, "confidence": "高"},
                        {"finding": f"近两年「{user_input}」相关技术快速发展", "source_id": 5, "confidence": "中"},
                    ],
                    "trend_analysis": f"「{user_input}」领域的技术趋势呈现向工程化、标准化方向发展的特点，相关工具链和框架日趋成熟。",
                    "knowledge_gaps": ["部分细分领域资料不够充分", "实践案例需要更多一手经验补充"],
                    "action_items": [
                        {"priority": "高", "action": f"深入学习「{user_input}」核心概念和原理"},
                        {"priority": "中", "action": f"动手实践「{user_input}」的典型应用场景"},
                        {"priority": "低", "action": "关注社区最新动态和版本更新"},
                    ],
                    "executive_summary": f"本次调研围绕「{user_input}」展开，通过全网多源搜索和四维加权筛选，共获取10条高价值信息。当前领域发展活跃，技术方向明确。建议优先掌握核心原理，结合实际场景进行实践。主要技术趋势向标准化和工程化方向演进，值得持续关注。",
                }, ensure_ascii=False, indent=2)

        if wf_name == "repo-due-diligence":
            repo_name = user_input.replace("https://github.com/", "").rstrip("/")
            if aid == "recon":
                return json.dumps({
                    "repo_name": repo_name,
                    "summary": f"{repo_name} 项目技术侦查报告。该项目活跃度高，社区健康，文档完善。",
                    "setup_complexity": "中等",
                    "first_impression": "文档清晰，入门门槛适中",
                    "notable_issues": [
                        {"id": "1234", "title": "Feature request", "importance": "中", "reason": "社区需求反馈"},
                    ],
                    "key_observations": "社区活跃，维护规范，代码质量良好。",
                }, ensure_ascii=False, indent=2)
            if aid == "code-review":
                return json.dumps({
                    "overall_scores": {"architecture": 4, "naming": 4, "testing": 3, "documentation": 4, "complexity": 3},
                    "key_risks": ["部分模块复杂度较高", "测试覆盖率有提升空间"],
                    "key_strengths": ["模块分离清晰", "命名规范一致", "代码风格统一"],
                }, ensure_ascii=False, indent=2)
            if aid == "health-metrics":
                return json.dumps({
                    "repo_name": repo_name,
                    "metrics": {
                        "commits_last_6m": random.randint(50, 200),
                        "commits_last_3m": random.randint(25, 100),
                        "pr_merge_median_hours": random.randint(12, 72),
                        "issue_response_median_hours": random.randint(6, 48),
                        "star_growth_6m_pct": random.randint(2, 10),
                        "star_growth_12m_pct": random.randint(5, 20),
                        "total_contributors": random.randint(50, 2000),
                        "core_contributors": random.randint(3, 15),
                        "bus_factor": random.randint(3, 10),
                        "last_release_date": f"2025-{random.randint(1,6):02d}",
                        "release_frequency": "每月",
                    },
                    "activity_trend": "上升",
                    "community_health": "健康",
                    "risk_flags": [],
                    "summary": f"{repo_name} 社区健康度良好，维护活跃。",
                }, ensure_ascii=False, indent=2)
            if aid == "usage-guide":
                return json.dumps({
                    "repo_name": repo_name,
                    "prerequisites": [{"name": "Node.js 18+", "how_to_check": "node -v"}],
                    "installation": {
                        "method": "包管理器",
                        "steps": [{"step": 1, "command": "npm install", "description": "安装依赖"}],
                        "one_liner": "npm install",
                    },
                    "quick_start": {"start_command": "npm start", "default_port": "http://localhost:3000"},
                    "common_commands": [{"command": "npm test", "description": "运行测试"}],
                    "usage_scenarios": [{"name": "开发", "description": "日常开发", "example": "npm run dev"}],
                    "platforms": ["Linux", "macOS", "Windows"],
                    "tips": ["建议使用最新版本"],
                }, ensure_ascii=False, indent=2)
            if aid == "risk-analyst":
                return json.dumps({
                    "repo_name": repo_name,
                    "recommendation": "推荐",
                    "recommendation_reason": f"{repo_name} 社区健康、维护活跃、代码质量良好，综合风险可控。",
                    "use_cases": {"production_critical": "适合", "side_project": "适合", "learning_reference": "适合"},
                    "risks": {
                        "tech_debt": {"level": "低", "detail": "代码质量良好", "mitigation": "保持版本更新"},
                        "maintenance": {"level": "低", "detail": "维护活跃", "mitigation": ""},
                        "community": {"level": "低", "detail": "社区健康", "mitigation": ""},
                        "license": {"level": "低", "detail": "MIT许可", "mitigation": ""},
                        "security": {"level": "低", "detail": "无已知漏洞", "mitigation": ""},
                    },
                    "alternatives": [],
                    "overall_assessment": f"{repo_name} 综合评估良好，推荐引入。",
                }, ensure_ascii=False, indent=2)

        if wf_name == "dev-workflow":
            proj = user_input[:20]
            if aid == "requirement":
                features = [f.strip() for f in user_input.replace("，", ",").split(",")[:5]]
                return json.dumps({
                    "project_name": proj,
                    "features": [{"name": f, "priority": "高", "dependencies": []} for f in features if f],
                }, ensure_ascii=False, indent=2)
            if aid == "architecture":
                return json.dumps({
                    "project_name": proj,
                    "modules": [{"name": "user", "description": "用户模块"}, {"name": "auth", "description": "认证模块"}],
                    "apis": [{"method": "GET", "path": "/api/users", "description": "获取用户列表"}],
                    "database": {"tables": ["users", "roles"]},
                    "tech_stack": {"backend": {"language": "Java 8", "framework": "SpringBoot 2.7"}, "frontend": {"framework": "Vue 3"}},
                }, ensure_ascii=False, indent=2)
            if aid.startswith("coding-"):
                return json.dumps({"module": aid, "status": "generated", "files": ["Controller.java", "Service.java", "Mapper.xml"]})
            if aid == "whitebox":
                return json.dumps({"summary": {"total_files_reviewed": 5, "issues_found": 2, "critical_issues": 0}, "overall_code_quality": "良好"})
            if aid == "blackbox":
                return json.dumps({"summary": {"total_test_cases": 12, "features_covered": 5, "apis_covered": 8}})
            if aid == "review":
                return json.dumps({
                    "project_name": proj,
                    "total_score": random.randint(75, 95),
                    "grade": "A",
                    "verdict": "可交付",
                    "executive_summary": f"「{proj}」项目综合评分良好，满足需求。",
                    "scores": {
                        "requirement_fit": {"score": 18, "max": 20, "comment": "需求覆盖完整"},
                        "architecture": {"score": 17, "max": 20, "comment": "架构合理"},
                        "code_quality": {"score": 16, "max": 20, "comment": "代码规范"},
                        "test_coverage": {"score": 14, "max": 20, "comment": "测试覆盖良好"},
                        "maintainability": {"score": 15, "max": 20, "comment": "可维护性高"},
                    },
                    "strengths": ["代码结构清晰", "文档完善"],
                    "weaknesses": ["部分模块可进一步优化"],
                    "blockers": [],
                    "improvement_roadmap": [{"priority": "低", "action": "补充单元测试", "expected_gain": "提高代码质量"}],
                }, ensure_ascii=False, indent=2)

        return json.dumps({"agent": aid, "task_id": task_id, "input": user_input}, ensure_ascii=False)

    def _render_final_report(self, wf_name: str, user_input: str, task_id: str, out_dir: Path) -> str:
        """Call the appropriate render script to produce the final MD report."""
        import subprocess

        now = datetime.now().strftime("%Y-%m-%d")
        topic = user_input.replace("/", "-").replace("\\", "-")[:40]

        if wf_name == "universal-search":
            filtered_json = out_dir / "3-filtered-results.json"
            doc_md = out_dir / "4-research-doc.md"
            summary_json = out_dir / "5-summary.json"
            template_md = ROOT_DIR / "universal-search" / "references" / "report-template.md"
            output_md = out_dir / f"FINAL-search-{topic}-{now}.md"
            render_script = ROOT_DIR / "universal-search" / "scripts" / "render_search_report.py"

            if render_script.exists() and filtered_json.exists():
                subprocess.run([
                    sys.executable, str(render_script),
                    str(filtered_json), str(doc_md), str(summary_json),
                    str(template_md), str(output_md),
                ], capture_output=True, timeout=30)
                return str(output_md)

        elif wf_name == "repo-due-diligence":
            recon_json = out_dir / "recon.json"
            code_review_json = out_dir / "code_review.json"
            health_json = out_dir / "health.json"
            risk_json = out_dir / "risk.json"
            usage_json = out_dir / "usage.json"
            template_md = ROOT_DIR / "repo-due-diligence" / "references" / "report-template.md"
            output_md = out_dir / f"due-diligence-{topic}-{now}.md"
            render_script = ROOT_DIR / "repo-due-diligence" / "scripts" / "render_report.py"

            if render_script.exists() and risk_json.exists():
                subprocess.run([
                    sys.executable, str(render_script),
                    str(recon_json), str(code_review_json), str(health_json),
                    str(risk_json), str(template_md), str(output_md),
                    str(usage_json),
                ], capture_output=True, timeout=30)
                return str(output_md)

        elif wf_name == "dev-workflow":
            review_json = out_dir / "5-review.json"
            arch_json = out_dir / "2-architecture.json"
            req_json = out_dir / "1-requirements.json"
            whitebox_json = out_dir / "4-whitebox.json"
            blackbox_json = out_dir / "4-blackbox.json"
            output_md = out_dir / f"FINAL-{topic}-{now}.md"
            render_script = ROOT_DIR / "dev-workflow" / "scripts" / "render_dev_report.py"

            if render_script.exists() and review_json.exists():
                subprocess.run([
                    sys.executable, str(render_script),
                    str(review_json), str(arch_json), str(req_json),
                    str(whitebox_json), str(blackbox_json), str(output_md),
                ], capture_output=True, timeout=30)
                return str(output_md)

        # Fallback: write a simple summary MD
        fallback_md = out_dir / f"FINAL-{topic}-{now}.md"
        fallback_md.write_text(
            f"# 执行报告：{user_input}\n\n**生成时间**：{self._now_full()}\n"
            f"**工作流**：{wf_name}\n**任务ID**：{task_id}\n\n"
            f"工作流已成功执行，相关 Agent 输出文件位于 `{out_dir}` 目录。\n",
            encoding="utf-8",
        )
        return str(fallback_md)

    # ── Legacy: agent update endpoint ────────────────────

    def _handle_agent_update(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"ok": False, "error": "Invalid JSON"}, 400)
            return

        wf_name = data.get("workflow")
        agent_id = data.get("agent_id")
        status = data.get("status", "running")
        progress = data.get("progress", 0)
        log_msg = data.get("log", "")
        children_done = data.get("children_done")

        self._update_agent_state(wf_name, agent_id, status, progress, log_msg, children_done)
        self._send_json({"ok": True})

    # ── Simulation (legacy demo) ─────────────────────────

    def _simulate_run(self):
        wf_order = ["repo-due-diligence", "dev-workflow"]
        for wf_name in wf_order:
            self._reset_state()
            state = self._load_state()
            state["active_workflow"] = wf_name
            state["started_at"] = self._now_full()
            state[wf_name]["status"] = "running"
            self._save_state(state)
            self._broadcast({"type": "state_update", "data": state})

            pipeline = self._load_pipeline()
            wf_def = pipeline["workflows"].get(wf_name, {})
            now = self._now_ts()

            for phase in wf_def.get("phases", []):
                state = self._load_state()
                state[wf_name]["phases"][phase["id"]]["status"] = "running"
                self._save_state(state)
                self._broadcast({"type": "state_update", "data": state})

                for agent_def in phase.get("agents", []):
                    aid = agent_def["id"]
                    agent = state[wf_name]["agents"][aid]
                    agent["status"] = "running"
                    agent["started_at"] = now
                    agent["log"].append(f"[{now}] 开始执行")

                    for p in range(0, 101, random.randint(15, 30)):
                        agent["progress"] = min(p, 90)
                        now = self._now_ts()
                        if "children" in agent_def:
                            agent["children_done"] = min(
                                int(agent_def["children"] * agent["progress"] / 100) + 1,
                                agent_def["children"],
                            )
                        self._save_state(state)
                        self._broadcast({"type": "state_update", "data": state})
                        time.sleep(random.uniform(0.1, 0.3))

                    agent["status"] = "done"
                    agent["progress"] = 100
                    agent["finished_at"] = self._now_ts()
                    agent["log"].append(f"[{agent['finished_at']}] 执行完成")
                    if "children" in agent_def:
                        agent["children_done"] = agent_def["children"]

                    self._save_state(state)
                    self._broadcast({"type": "state_update", "data": state})
                    time.sleep(0.15)

                state[wf_name]["phases"][phase["id"]]["status"] = "done"

            state[wf_name]["status"] = "done"
            self._save_state(state)
            self._broadcast({"type": "state_update", "data": state})

        self._broadcast({
            "type": "simulation_complete",
            "data": self._load_state(),
        })


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9138
    server = ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)
    print(f"Dashboard: http://127.0.0.1:{port}")
    print("按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
