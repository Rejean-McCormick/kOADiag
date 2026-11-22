"""C0 readiness checks: no real servers started."""
from __future__ import annotations

import contextlib
import io
import unittest
from unittest.mock import patch

from koa_ecosystem_diag import c0_reboot as mod


class Clock:
    def __init__(self): self.current = 0.0
    def __call__(self): return self.current
    def sleep(self, secs): self.current += secs


class C0ReadinessTests(unittest.TestCase):
    def test_waits_for_all_ports_not_first_one(self):
        clock = Clock()
        def check(port):
            if port == 21120: return clock.current >= 5.0
            if port == 21131: return clock.current >= 1.0
            raise AssertionError(port)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(mod.wait_for_ports(
                {'initkoa-web':21120, 'konnaxion-api':21131},
                timeout=10, interval=0.5, check=check,
                clock=clock, sleep=clock.sleep))
        self.assertGreaterEqual(clock.current, 5.5)

    def test_failed_service_times_out(self):
        clock=Clock()
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            result=mod.wait_for_ports({'initkoa-web':21120},timeout=2,
                interval=0.5,check=lambda port:False,clock=clock,sleep=clock.sleep)
        self.assertFalse(result)
        self.assertEqual(clock.current,2)
        self.assertIn('ECHEC DISPONIBILITÉ',output.getvalue())

    def test_transient_listener_not_counted_ready(self):
        clock=Clock()
        with contextlib.redirect_stdout(io.StringIO()):
            result=mod.wait_for_ports({'orgo-web':21110},timeout=1.2,
                interval=0.2,check=lambda port:clock.current <0.1,
                clock=clock,sleep=clock.sleep)
        self.assertFalse(result)

    def test_permanent_ready_returns_quickly(self):
        clock=Clock()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(mod.wait_for_ports({'orgo-web':21110},timeout=90,
                interval=.2,check=lambda port:True,clock=clock,sleep=clock.sleep))
        self.assertAlmostEqual(clock.current,.2)

    def test_invalid_deadline_rejected(self):
        with self.assertRaises(ValueError):mod.wait_for_ports({'x':123}, timeout=0)
        with self.assertRaises(ValueError):mod.wait_for_ports({}, timeout=1)

    def test_restart_failure_reported_in_return_code(self):
        """Smoke-test the integration path without touching any real process."""
        state={'processes':[]}
        selected={'initkoa-web':{'port':21120}}
        args=type('Args',(),{'command':'start','all':False,'groups':'initkoa','force_owned':False})()
        fake_spec={'kind':'process','label':'initkoa','ports':{'initkoa-web':21120}}
        out=io.StringIO()
        with patch.object(mod.os,'name','nt'), \
             patch.object(mod,'state_load',return_value=state), \
             patch.object(mod,'build_commands',return_value=[fake_spec]), \
             patch.object(mod,'managed_for',return_value=[]), \
             patch.object(mod,'check_port',return_value=False), \
             patch.object(mod,'launch_process',return_value=None), \
             patch.object(mod,'wait_for_ports',return_value=False), \
             contextlib.redirect_stdout(out):
            ret=mod.run_action(args,selected)
        self.assertEqual(ret,2)
        self.assertIn('groupes en erreur = 1',out.getvalue())


if __name__ == '__main__': unittest.main()
