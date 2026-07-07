"""
网络数据加载器（适配器组件）

负责从 LibSignal 原始配置中读取 SUMO 或 CityFlow 路网，
并转换为 Dashboard 需要的统一 network_data 结构。
"""

import json
import math
import os
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def _require_sumolib():
    if 'SUMO_HOME' not in os.environ:
        raise EnvironmentError("请设置环境变量 'SUMO_HOME'")

    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    if tools not in sys.path:
        sys.path.append(tools)

    import sumolib  # type: ignore
    return sumolib


def _load_sim_config(runtime_root: Path, network_name: str) -> Dict[str, Any]:
    cfg_path = runtime_root / 'configs' / 'sim' / f'{network_name}.cfg'
    if not cfg_path.exists():
        try:
            from .config_converter import ConfigConverter
        except ImportError:
            from config_converter import ConfigConverter

        resolved_path = None
        for world_name in ('sumo', 'cityflow'):
            candidate = ConfigConverter.resolve_network(network_name, world_name)
            candidate_path = runtime_root / 'configs' / 'sim' / f'{candidate}.cfg'
            if candidate_path.exists():
                resolved_path = candidate_path
                break

        if resolved_path is None:
            raise FileNotFoundError(f"仿真配置不存在: {cfg_path}")
        cfg_path = resolved_path
    with open(cfg_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _infer_world(sim_config: Dict[str, Any], world: Optional[str]) -> str:
    if world in {'sumo', 'cityflow'}:
        return world

    roadnet_file = str(sim_config.get('roadnetFile', ''))
    if roadnet_file.endswith('.net.xml') or sim_config.get('combined_file'):
        return 'sumo'
    return 'cityflow'


class SumoNetworkDataLoader:
    """
    从 SUMO .net.xml 文件加载网络数据。
    """

    def __init__(self, net_file_path: str):
        sumolib = _require_sumolib()
        self.net = sumolib.net.readNet(net_file_path)
        self.edge_data = self._get_edge_data()
        self.lane_data = self._get_lane_data()
        self.node_data, self.intersection_data = self._get_node_data()

    def get_network_data(self) -> Dict[str, Any]:
        return {
            'lane': self.lane_data,
            'edge': self.edge_data,
            'origin': self._find_origin_edges(),
            'destination': self._find_destination_edges(),
            'node': self.node_data,
            'inter': self.intersection_data,
        }

    def _find_destination_edges(self):
        next_edges = {e: 0 for e in self.edge_data}
        for edge_id in self.edge_data:
            for next_edge in self.edge_data[edge_id]['incoming']:
                next_edges[next_edge] += 1
        return [e for e, count in next_edges.items() if count == 0]

    def _find_origin_edges(self):
        next_edges = {e: 0 for e in self.edge_data}
        for edge_id in self.edge_data:
            for next_edge in self.edge_data[edge_id]['outgoing']:
                next_edges[next_edge] += 1
        return [e for e, count in next_edges.items() if count == 0]

    def _get_edge_data(self):
        edge_data = {}
        for edge in self.net.getEdges():
            edge_id = str(edge.getID())
            edge_data[edge_id] = {
                'lanes': [str(lane.getID()) for lane in edge.getLanes()],
                'length': float(edge.getLength()),
                'outgoing': [str(out.getID()) for out in edge.getOutgoing()],
                'noutgoing': len(edge.getOutgoing()),
                'nlanes': len(edge.getLanes()),
                'incoming': [str(inc.getID()) for inc in edge.getIncoming()],
                'incnode': str(edge.getFromNode().getID()),
                'outnode': str(edge.getToNode().getID()),
                'speed': float(edge.getSpeed()),
                'incnode_coord': edge.getFromNode().getCoord(),
                'outnode_coord': edge.getToNode().getCoord(),
            }
        return edge_data

    def _get_lane_data(self):
        lane_data = {}
        for edge_id, edge in self.edge_data.items():
            for lane_id in edge['lanes']:
                lane = self.net.getLane(lane_id)
                outgoing = {}
                move_ids = []
                for conn in lane.getOutgoing():
                    to_lane_id = str(conn.getToLane().getID())
                    outgoing[to_lane_id] = {
                        'dir': str(conn.getDirection()),
                        'index': conn.getTLLinkIndex(),
                    }
                    move_ids.append(str(conn.getDirection()))

                lane_data[lane_id] = {
                    'length': lane.getLength(),
                    'speed': lane.getSpeed(),
                    'edge': edge_id,
                    'outgoing': outgoing,
                    'movement': ''.join(sorted(move_ids)),
                    'incoming': [],
                }

        for lane_id, lane in lane_data.items():
            for to_lane_id in lane['outgoing']:
                if to_lane_id in lane_data:
                    lane_data[to_lane_id]['incoming'].append(lane_id)

        return lane_data

    def _get_node_data(self):
        node_data = {}
        for node in self.net.getNodes():
            node_id = str(node.getID())
            node_data[node_id] = {
                'incoming': [str(edge.getID()) for edge in node.getIncoming()],
                'outgoing': [str(edge.getID()) for edge in node.getOutgoing()],
                'tlsindex': {
                    conn.getTLLinkIndex(): str(conn.getFromLane().getID())
                    for conn in node.getConnections()
                },
                'tlsindexdir': {
                    conn.getTLLinkIndex(): str(conn.getDirection())
                    for conn in node.getConnections()
                },
                'neighbours': [],
                'x': node.getCoord()[0],
                'y': node.getCoord()[1],
            }

        for node_id, node in node_data.items():
            neighbours = set()
            for edge_id in node['incoming']:
                outnode = self.edge_data[edge_id]['incnode']
                if outnode in node_data and "traffic_light" in self.net.getNode(outnode).getType():
                    neighbours.add(outnode)
            for edge_id in node['outgoing']:
                incnode = self.edge_data[edge_id]['outnode']
                if incnode in node_data and "traffic_light" in self.net.getNode(incnode).getType():
                    neighbours.add(incnode)
            node['neighbours'] = list(neighbours)

        intersection_data = {
            node_id: dict(data)
            for node_id, data in node_data.items()
            if "traffic_light" in self.net.getNode(node_id).getType()
        }

        for inter_id, inter in intersection_data.items():
            inter['have_tl'] = True
            incoming_lanes = []
            outgoing_lanes = []
            for edge_id in inter['incoming']:
                incoming_lanes.extend(self.edge_data.get(edge_id, {}).get('lanes', []))
            for edge_id in inter['outgoing']:
                outgoing_lanes.extend(self.edge_data.get(edge_id, {}).get('lanes', []))
            inter['incoming_lanes'] = incoming_lanes
            inter['outgoing_lanes'] = outgoing_lanes

        return node_data, intersection_data


class CityFlowNetworkDataLoader:
    """
    从 CityFlow roadnet.json 加载网络数据。
    """

    DIRECTION_MAPPING = {
        'go_straight': 's',
        'turn_left': 'l',
        'turn_right': 'r',
    }

    def __init__(self, roadnet_path: str):
        with open(roadnet_path, 'r', encoding='utf-8') as f:
            self.roadnet = json.load(f)

        self.intersections = self.roadnet['intersections']
        self.roads = self.roadnet['roads']
        self.road_map = {road['id']: road for road in self.roads}
        self.intersection_map = {inter['id']: inter for inter in self.intersections}
        self.road_adjacency = self._build_road_adjacency()
        self.edge_data = self._get_edge_data()
        self.lane_data = self._get_lane_data()
        self.node_data, self.intersection_data = self._get_node_data()

    def get_network_data(self) -> Dict[str, Any]:
        return {
            'lane': self.lane_data,
            'edge': self.edge_data,
            'origin': self._find_origin_edges(),
            'destination': self._find_destination_edges(),
            'node': self.node_data,
            'inter': self.intersection_data,
        }

    def _is_virtual(self, intersection: Dict[str, Any]) -> bool:
        return bool(intersection.get('virtual') or intersection.get('gt_virtual'))

    def _road_length(self, road: Dict[str, Any]) -> float:
        points = road.get('points', [])
        if len(points) < 2:
            return 0.0
        length = 0.0
        for idx in range(len(points) - 1):
            dx = points[idx + 1]['x'] - points[idx]['x']
            dy = points[idx + 1]['y'] - points[idx]['y']
            length += math.hypot(dx, dy)
        return length

    def _build_road_adjacency(self) -> Dict[str, Dict[str, Any]]:
        adjacency = {road_id: {'incoming': set(), 'outgoing': set(), 'lane_links': {}} for road_id in self.road_map}
        for inter in self.intersections:
            for road_link_index, road_link in enumerate(inter.get('roadLinks', [])):
                start_road = road_link['startRoad']
                end_road = road_link['endRoad']
                adjacency[start_road]['outgoing'].add(end_road)
                adjacency[end_road]['incoming'].add(start_road)

                lane_links = adjacency[start_road]['lane_links']
                lane_links.setdefault(road_link_index, {'road_link': road_link, 'to_road': end_road})
        return adjacency

    def _get_edge_data(self):
        edge_data = {}
        for road in self.roads:
            road_id = road['id']
            start_inter = road['startIntersection']
            end_inter = road['endIntersection']
            start_point = self.intersection_map[start_inter]['point']
            end_point = self.intersection_map[end_inter]['point']
            edge_data[road_id] = {
                'lanes': [f"{road_id}_{idx}" for idx, _ in enumerate(road.get('lanes', []))],
                'length': self._road_length(road),
                'outgoing': sorted(self.road_adjacency[road_id]['outgoing']),
                'noutgoing': len(self.road_adjacency[road_id]['outgoing']),
                'nlanes': len(road.get('lanes', [])),
                'incoming': sorted(self.road_adjacency[road_id]['incoming']),
                'incnode': start_inter,
                'outnode': end_inter,
                'speed': max((lane.get('maxSpeed', 0.0) for lane in road.get('lanes', [])), default=0.0),
                'incnode_coord': (start_point['x'], start_point['y']),
                'outnode_coord': (end_point['x'], end_point['y']),
            }
        return edge_data

    def _get_lane_data(self):
        lane_data = {}
        for road in self.roads:
            road_id = road['id']
            road_length = self._road_length(road)
            for lane_index, lane in enumerate(road.get('lanes', [])):
                lane_id = f"{road_id}_{lane_index}"
                outgoing = {}
                movement = []

                end_intersection = self.intersection_map.get(road['endIntersection'], {})
                for link_index, road_link in enumerate(end_intersection.get('roadLinks', [])):
                    if road_link.get('startRoad') != road_id:
                        continue
                    for lane_link in road_link.get('laneLinks', []):
                        if lane_link.get('startLaneIndex') != lane_index:
                            continue
                        to_lane_id = f"{road_link['endRoad']}_{lane_link['endLaneIndex']}"
                        move_code = self.DIRECTION_MAPPING.get(road_link.get('type'), 's')
                        outgoing[to_lane_id] = {
                            'dir': move_code,
                            'index': link_index,
                        }
                        movement.append(move_code)

                lane_data[lane_id] = {
                    'length': road_length,
                    'speed': lane.get('maxSpeed', 0.0),
                    'edge': road_id,
                    'outgoing': outgoing,
                    'movement': ''.join(sorted(set(movement))),
                    'incoming': [],
                }

        for lane_id, lane in lane_data.items():
            for to_lane_id in lane['outgoing']:
                if to_lane_id in lane_data:
                    lane_data[to_lane_id]['incoming'].append(lane_id)

        return lane_data

    def _get_node_data(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        node_data = {}
        for inter in self.intersections:
            inter_id = inter['id']
            point = inter['point']
            incoming = []
            outgoing = []
            for road in self.roads:
                if road['endIntersection'] == inter_id:
                    incoming.append(road['id'])
                if road['startIntersection'] == inter_id:
                    outgoing.append(road['id'])

            neighbours = set()
            for road_id in incoming:
                neighbours.add(self.road_map[road_id]['startIntersection'])
            for road_id in outgoing:
                neighbours.add(self.road_map[road_id]['endIntersection'])

            node_data[inter_id] = {
                'incoming': incoming,
                'outgoing': outgoing,
                'tlsindex': {},
                'tlsindexdir': {},
                'neighbours': sorted(neighbours),
                'x': point['x'],
                'y': point['y'],
            }

        intersection_data = {}
        for inter in self.intersections:
            if self._is_virtual(inter):
                continue
            inter_id = inter['id']
            inter_info = dict(node_data[inter_id])
            inter_info['have_tl'] = True

            incoming_lanes = []
            outgoing_lanes = []
            for edge_id in inter_info['incoming']:
                incoming_lanes.extend(self.edge_data.get(edge_id, {}).get('lanes', []))
            for edge_id in inter_info['outgoing']:
                outgoing_lanes.extend(self.edge_data.get(edge_id, {}).get('lanes', []))

            inter_info['incoming_lanes'] = incoming_lanes
            inter_info['outgoing_lanes'] = outgoing_lanes
            intersection_data[inter_id] = inter_info

        return node_data, intersection_data

    def _find_origin_edges(self):
        return [edge_id for edge_id, edge in self.edge_data.items() if not edge['incoming']]

    def _find_destination_edges(self):
        return [edge_id for edge_id, edge in self.edge_data.items() if not edge['outgoing']]


def load_network_from_runtime(network_name='81', runtime_root=None, world=None):
    """
    从 runtime 系统加载网络数据。
    """
    if runtime_root is None:
        runtime_root = Path(__file__).parent.parent / 'runtime'
    else:
        runtime_root = Path(runtime_root)

    sim_config = _load_sim_config(runtime_root, network_name)
    resolved_world = _infer_world(sim_config, world)
    data_root = runtime_root / sim_config.get('dir', 'data')
    roadnet_path = data_root / sim_config['roadnetFile']

    if not roadnet_path.exists():
        raise FileNotFoundError(f"路网文件不存在: {roadnet_path}")

    if resolved_world == 'cityflow':
        loader = CityFlowNetworkDataLoader(str(roadnet_path))
    else:
        loader = SumoNetworkDataLoader(str(roadnet_path))

    network_data = loader.get_network_data()
    print(
        f"[load_network_from_runtime] world={resolved_world}, network={network_name}, "
        f"路口={len(network_data.get('inter', {}))}, 车道={len(network_data.get('lane', {}))}, "
        f"道路={len(network_data.get('edge', {}))}"
    )
    return network_data


# 向后兼容旧名称，避免渐进迁移期间的外层调用失效。
load_network_from_trainer = load_network_from_runtime


# 向后兼容旧接口名称。旧版 adapter 默认只支持 SUMO，
# 因此将旧名保留为 SUMO 加载器别名。
NetworkDataLoader = SumoNetworkDataLoader


def save_network_data_cache(network_data, cache_path):
    """
    保存网络数据到缓存文件。
    """
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, 'wb') as f:
        pickle.dump(network_data, f)


def load_network_data_cache(cache_path):
    """
    从缓存文件读取网络数据。
    """
    with open(cache_path, 'rb') as f:
        return pickle.load(f)
