#!/usr/bin/env python3
"""按确定性比例复制 SUMO route 文件中的车辆。"""

import argparse
import copy
import xml.etree.ElementTree as ET
from pathlib import Path


def indent(element, level=0):
    whitespace = '\n' + '    ' * level
    child_whitespace = '\n' + '    ' * (level + 1)
    children = list(element)
    if children:
        if not element.text or not element.text.strip():
            element.text = child_whitespace
        for child in children:
            indent(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = child_whitespace
        children[-1].tail = whitespace


def scale_flow(source, output, factor):
    if factor < 1:
        raise ValueError('factor 必须大于等于 1')

    tree = ET.parse(source)
    root = tree.getroot()
    vehicles = [child for child in root if child.tag == 'vehicle']
    extra_count = round(len(vehicles) * (factor - 1))
    if extra_count > len(vehicles):
        raise ValueError('当前工具仅支持 1.0 到 2.0 倍扩增')

    # 在完整时间序列中均匀选取车辆，保持全局时段与 OD 分布。
    selected_indices = {
        min(len(vehicles) - 1, int(index * len(vehicles) / extra_count))
        for index in range(extra_count)
    } if extra_count else set()

    vehicle_index = 0
    expanded_children = []
    existing_ids = {vehicle.get('id') for vehicle in vehicles}
    for child in list(root):
        expanded_children.append(child)
        if child.tag != 'vehicle':
            continue
        if vehicle_index in selected_indices:
            duplicate = copy.deepcopy(child)
            duplicate_id = f"{child.get('id')}__global15"
            suffix = 1
            while duplicate_id in existing_ids:
                duplicate_id = f"{child.get('id')}__global15_{suffix}"
                suffix += 1
            duplicate.set('id', duplicate_id)
            existing_ids.add(duplicate_id)
            expanded_children.append(duplicate)
        vehicle_index += 1

    root[:] = expanded_children
    indent(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output, encoding='utf-8', xml_declaration=True)
    return len(vehicles), sum(1 for child in root if child.tag == 'vehicle')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--factor', type=float, default=1.5)
    args = parser.parse_args()
    before, after = scale_flow(args.source, args.output, args.factor)
    print(f'车辆数: {before} -> {after} ({after / before:.2f}x)')
    print(f'输出: {args.output}')


if __name__ == '__main__':
    main()
