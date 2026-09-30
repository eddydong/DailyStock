import threading
import time
import unittest
from operator import add
from types import SimpleNamespace
from typing import Annotated

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from tradingagents.graph.analyst_execution import (
    analyst_waves,
    build_analyst_execution_plan,
)
from tradingagents.graph.setup import connect_analyst_waves


class AnalystExecutionPlanTests(unittest.TestCase):
    def test_build_plan_preserves_selected_order(self):
        plan = build_analyst_execution_plan(["news", "market"])

        self.assertEqual([spec.key for spec in plan.specs], ["news", "market"])
        self.assertEqual(plan.specs[0].agent_node, "News Analyst")
        self.assertEqual(plan.specs[0].tool_node, "tools_news")
        self.assertEqual(plan.specs[0].clear_node, "Msg Clear News")

    def test_rejects_unknown_analyst_keys(self):
        with self.assertRaises(ValueError):
            build_analyst_execution_plan(["market", "macro"])

    def test_social_key_displays_as_sentiment_analyst(self):
        # The wire key stays "social" for saved-config back-compat, but the
        # user-visible agent_node label must match the v0.2.5 rename so the
        # wall-time summary and any future consumer of agent_node says
        # "Sentiment Analyst" rather than the legacy "Social Analyst".
        plan = build_analyst_execution_plan(["social"])
        spec = plan.specs[0]
        self.assertEqual(spec.key, "social")
        self.assertEqual(spec.agent_node, "Sentiment Analyst")
        self.assertEqual(spec.report_key, "sentiment_report")

    def test_waves_stay_at_the_configured_width(self):
        specs = build_analyst_execution_plan(
            ["market", "social", "news", "fundamentals"], concurrency=2
        ).specs
        waves = analyst_waves(specs, 2)
        self.assertEqual([[spec.key for spec in wave] for wave in waves],
                         [["market", "social"], ["news", "fundamentals"]])
        self.assertEqual(len(analyst_waves(specs, 1)), 4)


class _WaveState(TypedDict):
    events: Annotated[list, add]


class WaveTimingTests(unittest.TestCase):
    def test_a_wave_overlaps_and_the_next_wave_waits(self):
        spans = {}

        def node(name, delay):
            def run(state):
                started = time.monotonic()
                time.sleep(delay)
                spans[name] = (started, time.monotonic())
                return {"events": [name]}
            return run

        workflow = StateGraph(_WaveState)
        for name, delay in (("a", 0.15), ("b", 0.15), ("c", 0.01)):
            workflow.add_node(name, node(name, delay))
        workflow.add_node("tail", node("tail", 0))
        specs = [SimpleNamespace(agent_node=name) for name in ("a", "b", "c")]
        connect_analyst_waves(workflow, analyst_waves(specs, 2), "tail")
        workflow.add_edge("tail", END)
        result = workflow.compile().invoke({"events": []})

        self.assertCountEqual(result["events"][:2], ["a", "b"])
        self.assertEqual(result["events"][-2:], ["c", "tail"])
        a0, a1 = spans["a"]
        b0, b1 = spans["b"]
        c0, _c1 = spans["c"]
        self.assertLess(a0, b1)
        self.assertLess(b0, a1)
        self.assertGreaterEqual(c0, max(a1, b1))


class VendorGateTests(unittest.TestCase):
    def test_yahoo_fetches_do_not_overlap(self):
        from tradingagents.dataflows.vendors.yahoo.ohlcv import yf_retry

        order = []
        lock = threading.Lock()

        def slow():
            with lock:
                order.append("in")
            time.sleep(0.05)
            with lock:
                order.append("out")

        threads = [threading.Thread(target=lambda: yf_retry(slow)) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(order, ["in", "out", "in", "out"])
