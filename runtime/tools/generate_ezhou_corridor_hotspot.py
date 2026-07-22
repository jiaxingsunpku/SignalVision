"""基于全局 1.5x 车流生成鄂州局部走廊高压测试集。"""

from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET


SOURCE_NAME = "ezhou_congested_3x_global_1_5x.rou.xml"
OUTPUT_NAME = "ezhou_corridor_hotspot_4x.rou.xml"

# J058 -> J014 的北部纵向主走廊。只要车辆经过其中任一段，就额外复制三份，
# 从而形成非对称局部冲击，而不继续均匀放大全路网需求。
HOTSPOT_EDGES = {
    "457722337#2.1396",
    "457722337#3",
    "457722337#4",
    "457722337#5",
}


def generate(source: Path, output: Path) -> tuple[int, int]:
    tree = ET.parse(source)
    root = tree.getroot()
    vehicles = list(root.findall("vehicle"))
    generated = []
    selected = 0

    for vehicle in vehicles:
        generated.append(vehicle)
        route = vehicle.find("route")
        edges = set(route.get("edges", "").split()) if route is not None else set()
        if not edges.intersection(HOTSPOT_EDGES):
            continue

        selected += 1
        depart = float(vehicle.get("depart", "0"))
        for copy_index, offset in enumerate((0.18, 0.36, 0.54), start=1):
            duplicate = deepcopy(vehicle)
            duplicate.set("id", f"{vehicle.get('id')}__corridor{copy_index}")
            duplicate.set("depart", f"{depart + offset:.2f}")
            generated.append(duplicate)

    for vehicle in vehicles:
        root.remove(vehicle)
    generated.sort(key=lambda item: (float(item.get("depart", "0")), item.get("id", "")))
    root.extend(generated)

    ET.indent(tree, space="    ")
    tree.write(output, encoding="utf-8", xml_declaration=True)
    return len(vehicles), selected


def main() -> None:
    data_dir = Path(__file__).resolve().parents[1] / "data" / "raw_data" / "ezhou"
    source = data_dir / SOURCE_NAME
    output = data_dir / OUTPUT_NAME
    original_count, selected_count = generate(source, output)
    print(
        f"generated {output}: {original_count + selected_count * 3} vehicles "
        f"({selected_count} corridor vehicles x4)"
    )


if __name__ == "__main__":
    main()
