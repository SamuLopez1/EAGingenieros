import unittest
from unittest.mock import Mock, patch

from scripts import smoke_local


class SmokeLocalTests(unittest.TestCase):
    def test_occupied_port_prevents_startup(self) -> None:
        for port in (smoke_local.API_PORT, smoke_local.WEB_PORT):
            with self.subTest(port=port), patch(
                "scripts.smoke_local.socket.socket"
            ) as socket_factory, patch("scripts.smoke_local.subprocess.Popen") as start_process:
                probe = socket_factory.return_value.__enter__.return_value
                probe.connect_ex.side_effect = lambda address: 0 if address[1] == port else 1

                with self.assertRaisesRegex(RuntimeError, rf"{port} to be free"):
                    smoke_local.main()

                start_process.assert_not_called()

    def test_exited_process_cannot_supply_a_ready_response(self) -> None:
        process = Mock()
        process.poll.return_value = 1

        with patch("scripts.smoke_local.urlopen") as request:
            with self.assertRaisesRegex(RuntimeError, "exited with code 1"):
                smoke_local.wait_for("http://127.0.0.1:8000/health", process)

        request.assert_not_called()
