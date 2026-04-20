from __future__ import annotations

from pathlib import Path

from business_panel.config import load_settings
from business_panel.server import make_server
from business_panel.status_service import PanelApplication


def main() -> None:
    root_dir = Path(__file__).resolve().parent.parent
    settings = load_settings(root_dir)
    app = PanelApplication(settings)
    server = make_server(settings.panel_host, settings.panel_port, app)
    print(f"Business panel listening on http://{settings.panel_host}:{settings.panel_port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
