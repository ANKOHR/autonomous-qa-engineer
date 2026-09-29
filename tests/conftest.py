from __future__ import annotations

import threading

import pytest

from aqe.fixtures import start_fixture_server


@pytest.fixture
def fixture_server():
    servers = []
    threads = []

    def start(app_name: str) -> str:
        server = start_fixture_server(app_name)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append(server)
        threads.append(thread)
        return f"http://127.0.0.1:{server.server_address[1]}/"

    yield start

    for server in servers:
        server.shutdown()
        server.server_close()
    for thread in threads:
        thread.join(timeout=2)
