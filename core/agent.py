"""RTL Agent with tool use via pluggable LLM backends.

The agent iterates on designs, evaluating correctness and cost.
Best result (lowest cost for 100% correct design) is tracked.
"""

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.cost import CostMetric, YosysTransistorCost
from core.evaluation import evaluate
from core.llm_client import LLMClient, TokenUsage
from core.prompts import build_amaranth_system_prompt, build_spirehdl_system_prompt, build_system_prompt
from tech_eval.ppa_extract.core.template import target_delay_time_unit

def _build_tools(target_delay_is_settable: bool) -> list:
    """Build the tool definitions list for the agent.

    When target_delay_is_settable is True the run_evaluation tool exposes an
    optional target_delay parameter so the LLM can override the synthesis
    timing constraint per evaluation.
    """
    run_eval_props: dict = {
        "filename": {
            "type": "string",
            "description": "Main design file to evaluate (e.g. 'design.sv' or 'design.py')",
        },
    }
    if target_delay_is_settable:
        run_eval_props["target_delay"] = {
            "type": "number",
            "description": f"Optional target delay in {target_delay_time_unit} to override the default for this evaluation.",
        }

    return [
        {
            "type": "function",
            "function": {
                "name": "create_file",
                "description": "Create a new file with the given content in the working directory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "Name of the file to create"},
                        "content": {"type": "string", "description": "Content to write to the file"},
                    },
                    "required": ["filename", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "replace_file",
                "description": "Replace the entire contents of an existing file with new content",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "Name of the file to replace"},
                        "content": {"type": "string", "description": "New content to write to the file"},
                    },
                    "required": ["filename", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "apply_diff",
                "description": "Apply a unified diff (git diff format) to modify a file. Include context lines for accurate patching.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "Name of the file to patch"},
                        "diff": {"type": "string", "description": "Unified diff content (git diff format) to apply"},
                    },
                    "required": ["filename", "diff"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "edit_file",
                "description": "Edit a file by replacing an exact string match with new content. The old_string must match exactly (including whitespace/indentation). Use this instead of apply_diff for simple, targeted edits.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "Name of the file to edit"},
                        "old_string": {"type": "string", "description": "Exact string to find in the file (must match uniquely)"},
                        "new_string": {"type": "string", "description": "Replacement string"},
                    },
                    "required": ["filename", "old_string", "new_string"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ls",
                "description": "List files in the working directory",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a file in the working directory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "Name of the file to read"},
                    },
                    "required": ["filename"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_evaluation",
                "description": "Run evaluation on the design. Returns correctness (pass/fail, checks) and cost.",
                "parameters": {
                    "type": "object",
                    "properties": run_eval_props,
                    "required": ["filename"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "done",
                "description": "Signal that the task is complete. Runs final evaluation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "Final message or summary"},
                    },
                    "required": [],
                },
            },
        },
    ]


@dataclass
class AgentResult:
    """Result of running the agent on a benchmark."""
    benchmark_name: str
    model: str
    passed: bool
    best_cost: Optional[float]
    cost_metric_name: str
    best_eval: Optional[Dict[str, Any]]
    all_evals: List[Dict[str, Any]]
    num_steps: int
    messages: List[Dict[str, Any]]
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    duration_s: float = 0.0
    error: str = ""
    best_metrics: Optional[Dict[str, float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "benchmark_name": self.benchmark_name,
            "model": self.model,
            "passed": self.passed,
            "best_cost": self.best_cost,
            "cost_metric": self.cost_metric_name,
            "best_metrics": self.best_metrics,
            "best_eval": self.best_eval,
            "all_evals": self.all_evals,
            "num_steps": self.num_steps,
            "token_usage": {
                "input_tokens": self.token_usage.input_tokens,
                "output_tokens": self.token_usage.output_tokens,
                "cache_creation_input_tokens": self.token_usage.cache_creation_input_tokens,
                "cache_read_input_tokens": self.token_usage.cache_read_input_tokens,
                "total_input_tokens": self.token_usage.total_input,
            },
            "duration_s": self.duration_s,
            "error": self.error,
        }


class RTLAgent:
    def __init__(
        self,
        client: LLMClient,
        workdir: Optional[Path] = None,
        max_steps: int = 20,
        cost_metric: Optional[CostMetric] = None,
        system_prompt_extra: str = "",
        language: str = "verilog",
        save_workspaces: bool = True,
        flowy_optimize: bool = False,
        abc_optimize: bool = False,
        arith_autoconfig: bool = False,
        dont_touch_main_arith: bool = False,
        fsm_optimize: bool = False,
        run_cec: bool = True,
        cec_reference: Optional[Path] = None,
    ):
        self.client = client
        self.model = client.model
        self.max_steps = max_steps
        self.cost_metric = cost_metric or YosysTransistorCost()
        self._default_target_delay = getattr(self.cost_metric, "target_delay", None)
        self.system_prompt_extra = system_prompt_extra
        self.language = language
        self.save_workspaces = save_workspaces
        self.flowy_optimize = flowy_optimize
        self.abc_optimize = abc_optimize
        self.arith_autoconfig = arith_autoconfig
        self.dont_touch_main_arith = dont_touch_main_arith
        self.fsm_optimize = fsm_optimize
        self.run_cec = run_cec
        self.cec_reference = cec_reference
        self.target_delay_is_settable = hasattr(self.cost_metric, "target_delay")
        self._tools = _build_tools(self.target_delay_is_settable)

        if workdir is None:
            self.workdir = Path(tempfile.mkdtemp(prefix="rtl_agent_"))
        else:
            self.workdir = workdir
            self.workdir.mkdir(parents=True, exist_ok=True)

        # Agent operates on files inside workspace/ subdirectory
        self.workspace = self.workdir / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.messages: List[Dict[str, Any]] = []
        self.is_done = False
        self.all_evals: List[Dict[str, Any]] = []
        self.best_eval: Optional[Dict[str, Any]] = None
        self.best_cost: Optional[float] = None
        self.best_metrics: Optional[Dict[str, float]] = None
        self._last_step_usage: Optional[TokenUsage] = None

        # Benchmark info (set before running)
        self.design_top_module: Optional[str] = None

    def _safe_path(self, filename: str) -> Optional[Path]:
        filepath = (self.workspace / filename).resolve()
        if not str(filepath).startswith(str(self.workspace.resolve())):
            return None
        return filepath

    def _safe_write_path(self, filename: str) -> Optional[Path]:
        """Like _safe_path but also forbids overwriting the testbench."""
        filepath = self._safe_path(filename)
        if filepath is None:
            return None
        if filepath.name == "tb.sv":
            return None
        return filepath

    def _execute_tool(self, tool_name: str, arguments: dict) -> str:
        try:
            if tool_name == "create_file":
                return self._create_file(arguments["filename"], arguments["content"])
            elif tool_name == "replace_file":
                return self._replace_file(arguments["filename"], arguments["content"])
            elif tool_name == "apply_diff":
                return self._apply_diff(arguments["filename"], arguments["diff"])
            elif tool_name == "edit_file":
                return self._edit_file(arguments["filename"], arguments["old_string"], arguments["new_string"])
            elif tool_name == "ls":
                return self._ls()
            elif tool_name == "read_file":
                return self._read_file(arguments["filename"])
            elif tool_name == "run_evaluation":
                return self._run_evaluation(arguments.get("filename", ""),
                                            target_delay=arguments.get("target_delay"))
            elif tool_name == "done":
                return self._done(arguments.get("message", ""))
            else:
                return f"Unknown tool: {tool_name}"
        except Exception as e:
            return f"Error executing tool {tool_name}: {e}"

    def _create_file(self, filename: str, content: str) -> str:
        filepath = self._safe_write_path(filename)
        if filepath is None:
            return "Error: Invalid filename (path traversal or protected file)"
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content)
            return f"Created file: {filename}"
        except Exception as e:
            return f"Error creating file: {e}"

    def _replace_file(self, filename: str, content: str) -> str:
        filepath = self._safe_write_path(filename)
        if filepath is None:
            return "Error: Invalid filename (path traversal or protected file)"
        if not filepath.exists():
            # Allow replace to also create if file doesn't exist
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content)
            return f"Created file (did not exist): {filename}"
        try:
            filepath.write_text(content)
            return f"Replaced file: {filename}"
        except Exception as e:
            return f"Error replacing file: {e}"

    @staticmethod
    def _apply_codex_patch(content: str, diff: str) -> str:
        """Apply a Codex-format patch (*** Begin Patch) to file content.

        Returns the patched content, or raises ValueError on failure.
        """
        lines = content.splitlines(keepends=True)
        # Strip envelope lines
        diff_lines = diff.splitlines(keepends=True)
        # Remove *** Begin Patch, *** End Patch, *** Update File lines
        hunks_raw: list = []
        current_hunk: list = []
        for dl in diff_lines:
            stripped = dl.strip()
            if stripped.startswith("*** "):
                # Envelope line — start new hunk if we have one pending
                if current_hunk:
                    hunks_raw.append(current_hunk)
                    current_hunk = []
                continue
            if stripped.startswith("@@"):
                if current_hunk:
                    hunks_raw.append(current_hunk)
                    current_hunk = []
                # Extract optional context after @@
                after_at = stripped[2:].strip()
                if after_at:
                    current_hunk.append((" ", after_at))
                continue
            if not dl:
                continue
            prefix = dl[0]
            text = dl[1:].rstrip("\n").rstrip("\r")
            if prefix in (" ", "-", "+"):
                current_hunk.append((prefix, text))
            else:
                # Treat as context line (some models omit the space prefix)
                current_hunk.append((" ", dl.rstrip("\n").rstrip("\r")))
        if current_hunk:
            hunks_raw.append(current_hunk)

        if not hunks_raw:
            raise ValueError("No hunks found in Codex patch")

        # Apply each hunk by finding context lines in the file
        for hunk in hunks_raw:
            # Collect context and minus lines to locate the hunk
            search_lines = [text for prefix, text in hunk if prefix in (" ", "-")]
            if not search_lines:
                # Only additions — append at end
                for prefix, text in hunk:
                    if prefix == "+":
                        lines.append(text + "\n")
                continue

            # Find the position in the file where context matches
            file_text_lines = [l.rstrip("\n").rstrip("\r") for l in lines]
            match_start = None
            for i in range(len(file_text_lines) - len(search_lines) + 1):
                if file_text_lines[i:i + len(search_lines)] == search_lines:
                    match_start = i
                    break

            if match_start is None:
                raise ValueError(
                    f"Could not locate hunk context in file: {search_lines[:3]}..."
                )

            # Build replacement
            new_lines = []
            for prefix, text in hunk:
                if prefix == "-":
                    continue  # remove
                else:  # " " (context) or "+"
                    new_lines.append(text + "\n")

            lines[match_start:match_start + len(search_lines)] = new_lines

        return "".join(lines)

    def _apply_diff(self, filename: str, diff: str) -> str:
        filepath = self._safe_write_path(filename)
        if filepath is None:
            return "Error: Invalid filename (path traversal or protected file)"
        if not filepath.exists():
            return f"Error: File not found: {filename}"
        try:
            original_content = filepath.read_text()

            # Try Codex patch format first if detected
            if "*** Begin Patch" in diff or ("@@" in diff and "---" not in diff):
                try:
                    patched = self._apply_codex_patch(original_content, diff)
                    filepath.write_text(patched)
                    return f"Applied diff to: {filename}"
                except (ValueError, IndexError) as e:
                    filepath.write_text(original_content)
                    return f"Error applying diff: {e}"

            # Standard unified diff via patch command
            with tempfile.NamedTemporaryFile(mode="w", suffix=".diff", delete=False) as df:
                df.write(diff)
                diff_path = df.name
            try:
                result = subprocess.run(
                    ["patch", "--no-backup-if-mismatch", str(filepath), diff_path],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    return f"Applied diff to: {filename}"
                else:
                    filepath.write_text(original_content)
                    return f"Error applying diff: {result.stderr or result.stdout}"
            finally:
                os.unlink(diff_path)
        except Exception as e:
            return f"Error applying diff: {e}"

    def _edit_file(self, filename: str, old_string: str, new_string: str) -> str:
        filepath = self._safe_write_path(filename)
        if filepath is None:
            return "Error: Invalid filename (path traversal or protected file)"
        if not filepath.exists():
            return f"Error: File not found: {filename}"
        try:
            content = filepath.read_text()
            count = content.count(old_string)
            if count == 0:
                return "Error: old_string not found in file"
            if count > 1:
                return f"Error: old_string found {count} times — must match exactly once. Add more surrounding context to make it unique."
            new_content = content.replace(old_string, new_string, 1)
            filepath.write_text(new_content)
            return f"Edited file: {filename}"
        except Exception as e:
            return f"Error editing file: {e}"

    def _ls(self) -> str:
        files = []
        for root, dirs, filenames in os.walk(self.workspace):
            # Skip obj_dir from verilator
            dirs[:] = [d for d in dirs if d != "obj_dir"]
            rel_root = os.path.relpath(root, self.workspace)
            for fn in filenames:
                if rel_root == ".":
                    files.append(fn)
                else:
                    files.append(os.path.join(rel_root, fn))
        if not files:
            return "Working directory is empty"
        return "Files:\n" + "\n".join(sorted(files))

    def _read_file(self, filename: str) -> str:
        filepath = self._safe_path(filename)
        if filepath is None:
            return "Error: Invalid filename"
        if not filepath.exists():
            return f"Error: File not found: {filename}"
        try:
            return filepath.read_text()
        except Exception as e:
            return f"Error reading file: {e}"

    def _snapshot_best(self, eval_index, design_file=None) -> None:
        """Save a copy of the current design files as the best workspace."""
        best_dir = self.workdir / "best_design"
        if best_dir.exists():
            shutil.rmtree(best_dir)
        best_dir.mkdir()
        skip = {"obj_dir"}
        for item in self.workspace.iterdir():
            if item.name in skip:
                continue
            dest = best_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
        # Write a small metadata file
        meta = {
            "eval_index": eval_index,
            "best_cost": self.best_cost,
            "cost_metric": self.cost_metric.metric_name,
            "design_file": design_file,
        }
        (best_dir / "_best_meta.json").write_text(json.dumps(meta, indent=2))

    def _snapshot_eval(self, eval_index, eval_dict, summary_text) -> Path:
        """Save workspace, evaluation summary, and cost into eval_{i}/."""
        eval_dir = self.workdir / f"eval_{eval_index}"
        if eval_dir.exists():
            shutil.rmtree(eval_dir)
        eval_dir.mkdir()
        # Copy workspace
        shutil.copytree(
            self.workspace, eval_dir / "workspace",
            ignore=shutil.ignore_patterns("obj_dir", "_cec"),
        )
        # Save evaluation result and summary
        (eval_dir / "result.json").write_text(json.dumps(eval_dict, indent=2))
        (eval_dir / "summary.txt").write_text(summary_text)
        return eval_dir

    def _run_evaluation(self, design_file: str = "",
                        target_delay: Optional[float] = None) -> str:
        eval_index = len(self.all_evals) + 1

        # Validate design file if provided
        if design_file:
            filepath = self._safe_path(design_file)
            if filepath is None:
                return "Error: Invalid filename (path traversal detected)"
            if not filepath.exists():
                return f"Error: Design file not found: {design_file}"

        # Clean obj_dir before re-running
        obj_dir = self.workspace / "obj_dir"
        if obj_dir.exists():
            shutil.rmtree(obj_dir)

        if self._default_target_delay is not None:
            self.cost_metric.target_delay = target_delay if target_delay is not None else self._default_target_delay
        result = evaluate(self.workspace, self.design_top_module,
                          cost_metric=self.cost_metric, language=self.language,
                          design_file=design_file or None,
                          run_cec=self.run_cec, cec_reference=self.cec_reference)
        eval_dict = result.to_dict()
        eval_dict["eval_index"] = eval_index
        eval_dict["design_file"] = design_file or None
        eval_dict["target_delay"] = target_delay
        if self._last_step_usage is not None:
            eval_dict["context_window_tokens"] = self._last_step_usage.total_input
        self.all_evals.append(eval_dict)

        # Track best: lowest cost among 100% correct designs.  Ties are
        # broken by the metric's declared tiebreaker_key (e.g. delay→area,
        # aig_count→depth, yosys_wires→cells; None for transistors).
        if result.passed and result.cost.ok:
            cv = result.cost_value
            metrics = eval_dict.get("metrics") or {}
            tiebreaker_key = getattr(type(self.cost_metric), "tiebreaker_key", None)
            is_better = False
            if self.best_cost is None:
                is_better = True
            elif cv < self.best_cost:
                is_better = True
            elif cv == self.best_cost and tiebreaker_key:
                new_sec = metrics.get(tiebreaker_key)
                old_sec = (self.best_metrics or {}).get(tiebreaker_key)
                if new_sec is not None and (old_sec is None or new_sec < old_sec):
                    is_better = True
            if is_better:
                self.best_cost = cv
                self.best_eval = eval_dict
                self.best_metrics = metrics
                self._snapshot_best(eval_dict.get("eval_index", "?"),
                                    design_file=eval_dict.get("design_file"))

        metric = self.cost_metric.metric_name
        summary = result.summary_str()
        if self.best_cost is not None:
            summary += f"\n\nBest so far: {self.best_cost} {metric} (eval {self.best_eval.get('eval_index', '?')})"

        # Optionally snapshot workspace + results after evaluation
        if self.save_workspaces:
            eval_dir = self._snapshot_eval(eval_index, eval_dict, summary)
            summary = f"[Eval saved to {eval_dir.name}/]\n" + summary

        return summary

    def _done(self, message: str = "") -> str:
        self.is_done = True
        result = "=== Done: Task Complete ===\n"
        if message:
            result += f"Agent message: {message}\n"
        if self.best_eval:
            metric = self.cost_metric.metric_name
            result += f"\n\nBest result: {self.best_cost} {metric} (eval {self.best_eval.get('eval_index', '?')})"
        return result

    def run(self, description: str, benchmark_name: str = "unknown") -> AgentResult:
        """Run the agent loop on a given design task."""
        if self.language == "spirehdl":
            system_prompt = build_spirehdl_system_prompt(
                description, self.cost_metric.metric_name,
                self.system_prompt_extra,
                target_delay_is_settable=self.target_delay_is_settable,
                max_steps=self.max_steps,
                flowy_optimize=self.flowy_optimize,
                abc_optimize=self.abc_optimize,
                arith_autoconfig=self.arith_autoconfig,
                dont_touch_main_arith=self.dont_touch_main_arith,
                fsm_optimize=self.fsm_optimize,
            )
        elif self.language == "amaranth":
            system_prompt = build_amaranth_system_prompt(
                description, self.cost_metric.metric_name,
                self.system_prompt_extra,
                target_delay_is_settable=self.target_delay_is_settable,
                max_steps=self.max_steps,
            )
        else:
            system_prompt = build_system_prompt(
                description, self.cost_metric.metric_name,
                self.system_prompt_extra,
                target_delay_is_settable=self.target_delay_is_settable,
                max_steps=self.max_steps,
            )
        self.messages = [{"role": "system", "content": system_prompt}]
        self.is_done = False
        self.all_evals = []
        self.best_eval = None
        self.best_cost = None
        self.best_metrics = None
        total_usage = TokenUsage()

        # Initial user message to kick off the agent
        self.messages.append({
            "role": "user",
            "content": "Please create the design according to the specification. Start with a simple correct implementation, evaluate it, then optimize.",
        })

        step = 0
        while not self.is_done and step < self.max_steps:
            step += 1
            try:
                response = self.client.chat_completion(
                    messages=self.messages,
                    tools=self._tools,
                    tool_choice="auto",
                )
            except Exception as e:
                error_msg = f"API error on step {step}: {e}"
                print(f"\n  ERROR: {error_msg}")
                passed = self.best_eval is not None and self.best_eval.get("passed", False)
                return AgentResult(
                    benchmark_name=benchmark_name,
                    model=self.model,
                    passed=passed,
                    best_cost=self.best_cost,
                    cost_metric_name=self.cost_metric.metric_name,
                    best_eval=self.best_eval,
                    all_evals=self.all_evals,
                    num_steps=step,
                    messages=self.messages,
                    token_usage=total_usage,
                    error=error_msg,
                    best_metrics=self.best_metrics,
                )

            total_usage = total_usage + response.usage
            self._last_step_usage = response.usage

            # Build message dict for history
            msg_dict: Dict[str, Any] = {
                "role": "assistant",
                "content": response.content,
            }
            if response.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        },
                    }
                    for tc in response.tool_calls
                ]
            self.messages.append(msg_dict)
            
            # print message
            print(f"\nStep {step} - Agent response:")
            print(response.content)

            if not response.tool_calls:
                # No tool calls - add a reminder and continue
                if not self.is_done:
                    self.messages.append({
                        "role": "user",
                        "content": f"[Step {step}/{self.max_steps}] Please use a tool. If you are done, call the done tool.",
                    })
                continue

            # Execute tool calls
            for tool_call in response.tool_calls:
                tool_name = tool_call.name
                try:
                    arguments = json.loads(tool_call.arguments)
                except json.JSONDecodeError:
                    arguments = {}

                _arg_str = ", ".join(
                    f"{k}={repr(v)[:80]}" for k, v in arguments.items()
                )
                print(f"  [{step}] {tool_name}({_arg_str})")
                result = self._execute_tool(tool_name, arguments)
                # Truncate very long results to avoid context overflow,
                # but skip truncation for .py file reads (context files).
                skip_truncate = (
                    tool_name == "read_file"
                    and arguments.get("filename", "").endswith(".py")
                )
                if not skip_truncate and len(result) > 2000:
                    result = result[:2000] + "\n... (truncated)"
                print(f"    -> {result[:500]}")

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": f"[Step {step}/{self.max_steps}]\n{result}",
                })

            if self.is_done:
                break


        # tell reason why it ended
        if self.is_done:
            print(f"\nAgent signaled done after {step} steps.")
        else:
            print(f"\nReached max steps ({self.max_steps}) without agent signaling done.")

        # Ask the LLM for a summary and lessons learned
        total_usage = self._request_summary(total_usage)

        passed = self.best_eval is not None and self.best_eval.get("passed", False)
        return AgentResult(
            benchmark_name=benchmark_name,
            model=self.model,
            passed=passed,
            best_cost=self.best_cost,
            cost_metric_name=self.cost_metric.metric_name,
            best_eval=self.best_eval,
            all_evals=self.all_evals,
            num_steps=step,
            messages=self.messages,
            token_usage=total_usage,
            best_metrics=self.best_metrics,
        )

    def _request_summary(self, total_usage: TokenUsage) -> TokenUsage:
        """Ask the LLM to summarize the design process and lessons learned."""
        cost_str = f"{self.best_cost:.4g}" if self.best_cost is not None else "N/A"
        passed = self.best_eval is not None and self.best_eval.get("passed", False)

        self.messages.append({
            "role": "user",
            "content": (
                "The design session is now over. "
                f"Final result: {'PASS' if passed else 'FAIL'}, best cost: {cost_str} {self.cost_metric.metric_name}.\n\n"
                "Please write a brief summary covering:\n"
                "1. What approaches did you try and what worked best?\n"
                "2. What optimizations had the most impact?\n"
                "3. What didn't work or caused regressions?\n"
                "4. Lessons learned and what you would do differently next time.\n\n"
                "Your design files are carried over to the next agent, so refer to them by filename where useful.\n"
                "Be concise and specific."
            ),
        })

        try:
            response = self.client.chat_completion(
                messages=self.messages,
                tools=None,
                tool_choice=None,
            )
            total_usage = total_usage + response.usage
            summary_text = response.content or ""
            self.messages.append({
                "role": "assistant",
                "content": summary_text,
            })
            print(f"\n--- Agent Summary ---\n{summary_text}\n")

            # Save summary to a separate file
            summary_path = self.workdir / "summary.txt"
            summary_path.write_text(summary_text)

        except Exception as e:
            print(f"\n  Warning: could not generate summary: {e}")

        return total_usage
