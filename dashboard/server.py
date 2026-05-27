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
        """Generate mock structured output for an agent."""
        now = self._now_full()
        if wf_name == "universal-search":
            if aid == "search":
                return json.dumps({
                    "query": user_input,
                    "task_id": task_id,
                    "extracted_features": {
                        "keywords": [w.strip() for w in user_input.split()[:5]],
                        "domain": "技术",
                        "timeliness": "近一年",
                        "depth": "中等",
                    },
                    "total_results": 12,
                    "results": [{
                        "id": i,
                        "title": f"{user_input} 相关结果 {i}",
                        "url": f"https://example.com/result-{i}",
                        "summary": f"与 {user_input} 相关的搜索结果摘要 #{i}",
                        "source_type": "技术博客",
                        "publish_date": "2025-06-01",
                    } for i in range(1, 13)],
                }, ensure_ascii=False)
            if aid.startswith("scorer-"):
                n = aid.split("-")[1]
                return json.dumps({
                    "scorer_id": aid,
                    "query": user_input,
                    "results": [],
                    "retained_count": 1,
                    "discarded_count": 0,
                }, ensure_ascii=False)
            if aid == "judgment":
                return json.dumps({
                    "query": user_input,
                    "scorer_stats": {"total_scorers": 10, "total_retained": 10},
                    "filtered_count": 10,
                    "results": [],
                }, ensure_ascii=False)
            if aid == "summary":
                return json.dumps({
                    "query": user_input,
                    "date": now,
                    "key_findings": [{
                        "finding": f"关于 {user_input} 的核心发现",
                        "source_id": 1,
                        "confidence": "高",
                    }],
                    "executive_summary": f"本次调研围绕「{user_input}」展开，通过多源搜索与并行分拣筛选，获取了高质量信息。",
                }, ensure_ascii=False)

        if wf_name == "repo-due-diligence":
            if aid == "recon":
                return json.dumps({
                    "repo_name": user_input,
                    "summary": f"{user_input} 仓库技术侦查报告",
                    "setup_complexity": "中等",
                    "notable_issues": [],
                }, ensure_ascii=False)
            if aid == "risk-analyst":
                return json.dumps({
                    "repo_name": user_input,
                    "recommendation": "推荐",
                    "recommendation_reason": "综合评估后认为该仓库值得引入",
                }, ensure_ascii=False)

        if wf_name == "dev-workflow":
            if aid == "requirement":
                return json.dumps({
                    "project_name": user_input[:30],
                    "features": [{"name": f.strip(), "priority": "高"} for f in user_input.split(",")[:5]],
                }, ensure_ascii=False)
            if aid == "review":
                return json.dumps({
                    "project_name": user_input[:30],
                    "total_score": 85,
                    "grade": "B+",
                    "verdict": "可交付",
                }, ensure_ascii=False)

        return json.dumps({"agent": aid, "task_id": task_id, "input": user_input}, ensure_ascii=False)

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
