"""Zara - Agent Orchestrator (AIBrain-inspired multi-agent teams)

Enables Zara to spawn specialized sub-agents that work together on
complex tasks. Each agent has a specific role and can be chained into
workflows.
"""

from __future__ import annotations

import threading
import time
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from queue import Queue


class AgentRole(Enum):
    RESEARCHER = "researcher"      # Gathers information from web/files
    CODER = "coder"               # Writes and tests code
    REVIEWER = "reviewer"         # Reviews and critiques output
    SUMMARIZER = "summarizer"     # Condenses information
    PLANNER = "planner"           # Breaks down complex tasks
    EXECUTOR = "executor"         # Performs system actions


@dataclass
class AgentTask:
    """A task assigned to a sub-agent."""
    id: str
    role: AgentRole
    instruction: str
    context: str = ""
    result: Optional[str] = None
    status: str = "pending"  # pending, running, completed, failed


@dataclass
class Workflow:
    """A sequence of agent tasks that accomplish a complex goal."""
    name: str
    description: str
    tasks: List[AgentTask] = field(default_factory=list)
    on_complete: Optional[str] = None  # Final summary prompt


class AgentOrchestrator:
    """Manages multiple specialized agents working in parallel or sequence."""

    def __init__(self, llm_callback: Callable[[str, str], str]):
        """
        Args:
            llm_callback: Function that takes (system_prompt, user_prompt) 
                         and returns the LLM response.
        """
        self.llm_callback = llm_callback
        self.active_workflows: Dict[str, Workflow] = {}
        self.completed_tasks: List[AgentTask] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._task_queue: Queue = Queue()

    def start(self) -> None:
        """Start the orchestrator background thread."""
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print("[Orchestrator] Agent teams online.")

    def stop(self) -> None:
        self._running = False

    def _run_loop(self) -> None:
        """Process pending agent tasks."""
        while self._running:
            try:
                task: AgentTask = self._task_queue.get(timeout=1.0)
                self._execute_agent_task(task)
            except Exception:
                pass

    def _execute_agent_task(self, task: AgentTask) -> None:
        """Execute a single agent task using the appropriate role prompt."""
        task.status = "running"

        role_prompts = {
            AgentRole.RESEARCHER: (
                "You are a research agent. Your job is to gather accurate, "
                "concise information. Focus only on facts relevant to the query. "
                "Return raw information without commentary."
            ),
            AgentRole.CODER: (
                "You are a coding agent. Write clean, efficient Python code. "
                "Include error handling. Return ONLY the code block, no explanation."
            ),
            AgentRole.REVIEWER: (
                "You are a code reviewer. Analyze the provided code for bugs, "
                "security issues, and style problems. Be critical and thorough."
            ),
            AgentRole.SUMMARIZER: (
                "You are a summarization agent. Condense the provided information "
                "into 2-3 key bullet points. Be extremely concise."
            ),
            AgentRole.PLANNER: (
                "You are a planning agent. Break down the complex task into "
                "a step-by-step plan. Each step should be actionable."
            ),
            AgentRole.EXECUTOR: (
                "You are an execution agent. Generate the exact system command "
                "or action payload needed to accomplish the task."
            ),
        }

        system_prompt = role_prompts.get(
            task.role, "You are a helpful assistant.")
        full_prompt = f"{system_prompt}\n\nContext: {task.context}\n\nTask: {task.instruction}"

        try:
            # Call the LLM (could be Groq or local Ollama)
            result = self.llm_callback(system_prompt, task.instruction)
            task.result = result
            task.status = "completed"
            print(
                f"[Orchestrator] Agent {task.role.value} completed task {task.id}")
        except Exception as e:
            task.result = f"Error: {e}"
            task.status = "failed"
            print(f"[Orchestrator] Agent {task.role.value} failed: {e}")

        self.completed_tasks.append(task)

    def create_research_team(self, query: str) -> Workflow:
        """Create a team to research a topic and produce a summary."""
        import uuid

        workflow = Workflow(
            name=f"Research: {query[:30]}",
            description=query,
        )

        # Researcher gathers raw info
        research_task = AgentTask(
            id=str(uuid.uuid4())[:8],
            role=AgentRole.RESEARCHER,
            instruction=f"Research the following topic thoroughly: {query}",
        )
        workflow.tasks.append(research_task)

        # Summarizer condenses it
        workflow.on_complete = (
            "Take the research findings and produce a concise executive summary. "
            "Include the 3 most important points."
        )

        return workflow

    def create_coding_team(self, task_description: str, context_files: str = "") -> Workflow:
        """Create a team to write, review, and refine code."""
        import uuid

        workflow = Workflow(
            name=f"Code: {task_description[:30]}",
            description=task_description,
        )

        # Planner breaks down the task
        planner_task = AgentTask(
            id=str(uuid.uuid4())[:8],
            role=AgentRole.PLANNER,
            instruction=f"Create a step-by-step plan for: {task_description}",
            context=context_files,
        )
        workflow.tasks.append(planner_task)

        # Coder implements
        coder_task = AgentTask(
            id=str(uuid.uuid4())[:8],
            role=AgentRole.CODER,
            instruction=f"Implement the plan for: {task_description}",
        )
        workflow.tasks.append(coder_task)

        # Reviewer checks
        reviewer_task = AgentTask(
            id=str(uuid.uuid4())[:8],
            role=AgentRole.REVIEWER,
            instruction="Review the generated code for issues.",
        )
        workflow.tasks.append(reviewer_task)

        return workflow

    def execute_workflow(self, workflow: Workflow) -> str:
        """Run a workflow and return the final result."""
        results = []

        for i, task in enumerate(workflow.tasks):
            # Pass previous results as context
            if i > 0 and results:
                task.context = f"Previous step output:\n{results[-1]}"

            self._task_queue.put(task)

            # Wait for completion (simple approach—could be async)
            while task.status in ["pending", "running"]:
                time.sleep(0.1)

            if task.result:
                results.append(task.result)

        # Generate final summary if specified
        if workflow.on_complete and results:
            final_prompt = f"{workflow.on_complete}\n\nRaw findings:\n{results[-1]}"
            final_result = self.llm_callback(
                "You are a synthesis agent. Combine information into a polished final output.",
                final_prompt
            )
            return final_result

        return results[-1] if results else "Workflow completed with no output."


# Global singleton
_orchestrator: Optional[AgentOrchestrator] = None


def get_orchestrator(llm_callback: Callable = None) -> AgentOrchestrator:
    global _orchestrator
    if _orchestrator is None and llm_callback:
        _orchestrator = AgentOrchestrator(llm_callback)
    return _orchestrator
