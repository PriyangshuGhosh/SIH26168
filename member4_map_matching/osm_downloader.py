"""Optional OSM helpers. No hardcoded city. Match-time code must not import this for HTTP."""

from pathlib import Path

import networkx as nx


def load_graph(input_path: str):
    graph = nx.read_graphml(input_path)
    return graph


def save_graph(graph, output_path: str) -> None:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(graph, output_file)


if __name__ == "__main__":
    raise SystemExit(
        "Use python/tools/extract_osm.py --lat ... --lon ... --catalog ... "
        "(OpenStreetMap / Overpass, ODbL). Do not scrape map tiles."
    )
