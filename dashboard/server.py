#!/usr/bin/env python3
"""
Agent Pipeline Dashboard Server
提供 SSE 实时推送 + API + 静态文件服务
"""
import json
import time
import threading
import queue
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path
from typing import List

DASHBOARD_DIR = Path(__file__).parent.resolve()
STATE_FILE = DASHBOARD_DIR / "state.json"
PIPELINE_FILE = DASHBOARD_DIR / "pipeline.json"

# SSE 事件队列
event_queues: List[queue.Queue] = []


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程 HTTP 服务器"""
    daemon_threads = True


class DashboardHandler(SimpleHTTPRequestHandler):
    """支持 SSE + API + 静态文件 的 HTTP Handler"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def log_message(self, format, *args):
        # 简洁日志
        pass

    def do_GET(self):
        path = self.path.split("?")[0]

        # SSE 端点
        if path == "/api/events":
            self._handle_sse()
            return

        # API: 获取状态
        if path == "/api/state":
            self._send_json(self._load_state())
            return

        # API: 获取 pipeline 定义
        if path == "/api/pipeline":
            self._send_json(self._load_pipeline())
            return

        # API: 重置状态
        if path == "/api/reset":
            self._reset_state()
            self._broadcast({"type": "reset", "data": self._load_state()})
            self._send_json({"ok": True})
            return

        # 静态文件（默认回退到 index.html）
        if path == "/":
            self.path = "/index.html"

        super().do_GET()

    def do_POST(self):
        path = self.path.split("?")[0]

        # API: 更新 agent 状态
        if path == "/api/agent/update":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(body)
                result = self._update_agent(data)
                self._send_json({"ok": True, "result": result})
                self._broadcast({"type": "state_update", "data": self._load_state()})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 400)
            return

        # API: 启动工作流
        if path == "/api/workflow/start":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(body)
                self._start_workflow(data.get("workflow"))
                self._send_json({"ok": True})
                self._broadcast({"type": "workflow_started", "data": self._load_state()})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 400)
            return

        # API: 模拟运行（用于演示）
        if path == "/api/simulate":
            t = threading.Thread(target=self._simulate_run, daemon=True)
            t.start()
            self._send_json({"ok": True, "message": "模拟运行已启动，请观察面板"})
            return

        self.send_error(405)

    def _handle_sse(self):
        """Server-Sent Events 长连接"""
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
                    self.wfile.write(f"data: {json.dumps(msg, ensure_ascii=False)}\n\n".encode())
                    self.wfile.flush()
                except queue.Empty:
                    self.wfile.write(": heartbeat\n\n".encode())
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            event_queues.remove(q)

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
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _reset_state(self):
        initial = json.loads(
            (DASHBOARD_DIR / "state.json").read_text(encoding="utf-8")
        )
        self._save_state(initial)

    def _update_agent(self, data):
        workflow = data.get("workflow")
        agent_id = data.get("agent_id")
        status = data.get("status")  # running, done, failed
        progress = data.get("progress", 0)
        log_msg = data.get("log", "")
        children_done = data.get("children_done")

        state = self._load_state()
        agent = state[workflow]["agents"].get(agent_id)
        if not agent:
            return f"Agent {agent_id} not found in {workflow}"

        now = time.strftime("%H:%M:%S")
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

        # 更新 phase 状态
        pipeline = self._load_pipeline()
        wf_def = pipeline["workflows"][workflow]
        for phase in wf_def["phases"]:
            agent_ids = [a["id"] for a in phase["agents"]]
            agent_states = [state[workflow]["agents"][aid]["status"] for aid in agent_ids]
            if all(s == "done" for s in agent_states):
                state[workflow]["phases"][phase["id"]]["status"] = "done"
            elif any(s == "running" for s in agent_states):
                state[workflow]["phases"][phase["id"]]["status"] = "running"
            elif any(s == "failed" for s in agent_states):
                state[workflow]["phases"][phase["id"]]["status"] = "failed"

        # 更新整体状态
        all_done = all(
            state[workflow]["agents"][aid]["status"] == "done"
            for aid in state[workflow]["agents"]
        )
        any_running = any(
            state[workflow]["agents"][aid]["status"] == "running"
            for aid in state[workflow]["agents"]
        )
        if all_done:
            state[workflow]["status"] = "done"
        elif any_running:
            state[workflow]["status"] = "running"

        self._save_state(state)
        return f"Updated {workflow}/{agent_id} -> {status}"

    def _start_workflow(self, workflow):
        state = self._load_state()
        self._reset_state()
        state = self._load_state()
        state["active_workflow"] = workflow
        state["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        state[workflow]["status"] = "running"
        self._save_state(state)

    def _simulate_run(self):
        """模拟 complete 流水线运行（演示用）"""
        import random

        state = self._load_state()

        for wf_name in ["repo-due-diligence", "dev-workflow"]:
            state["active_workflow"] = wf_name
            state["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            state[wf_name]["status"] = "running"

            pipeline = self._load_pipeline()
            wf_def = pipeline["workflows"][wf_name]
            now = time.strftime("%H:%M:%S")

            for phase in wf_def["phases"]:
                state[wf_name]["phases"][phase["id"]]["status"] = "running"
                self._save_state(state)
                self._broadcast({"type": "state_update", "data": state})

                for agent_def in phase["agents"]:
                    aid = agent_def["id"]
                    agent = state[wf_name]["agents"][aid]

                    agent["status"] = "running"
                    agent["started_at"] = now
                    agent["log"].append(f"[{now}] 开始执行")

                    # 模拟进度
                    for p in range(0, 101, random.randint(15, 30)):
                        agent["progress"] = min(p, 90)
                        now = time.strftime("%H:%M:%S")
                        if "children" in agent_def:
                            agent["children_done"] = min(
                                int(agent_def["children"] * agent["progress"] / 100) + 1,
                                agent_def["children"]
                            )
                        self._save_state(state)
                        self._broadcast({"type": "state_update", "data": state})
                        time.sleep(random.uniform(0.15, 0.4))

                    agent["status"] = "done"
                    agent["progress"] = 100
                    agent["finished_at"] = time.strftime("%H:%M:%S")
                    agent["log"].append(f"[{agent['finished_at']}] 执行完成")
                    if "children" in agent_def:
                        agent["children_done"] = agent_def["children"]

                    self._save_state(state)
                    self._broadcast({"type": "state_update", "data": state})
                    time.sleep(0.2)

                state[wf_name]["phases"][phase["id"]]["status"] = "done"

            state[wf_name]["status"] = "done"

        self._save_state(state)
        self._broadcast({"type": "simulation_complete", "data": state})

    def _broadcast(self, msg):
        dead = []
        for q in event_queues:
            try:
                q.put_nowait(msg)
            except queue.Full:
                dead.append(q)
        for q in dead:
            event_queues.remove(q)


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
