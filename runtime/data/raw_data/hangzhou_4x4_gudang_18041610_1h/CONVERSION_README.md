# CityFlow到SUMO格式转换说明

## 转换完成

已成功将杭州4x4路网从CityFlow格式转换为SUMO格式！

## 源文件（CityFlow格式）

- **路网文件**: `roadnet_4X4.json` (35,718行)
- **交通流文件**: `hangzhou_4x4_gudang_18041610_1h.json`

## 生成的文件（SUMO格式）

### 1. 路网相关文件

- **`hangzhou_4x4_converted.nod.xml`** - 节点文件
  - 定义路网中所有交叉路口的位置和类型
  
- **`hangzhou_4x4_converted.edg.xml`** - 边文件
  - 定义路网中所有道路（边）的属性
  
- **`hangzhou_4x4_converted.con.xml`** - 连接文件
  - 定义交叉路口处车道之间的连接关系
  
- **`hangzhou_4x4_converted.tll.xml`** - 信号灯逻辑文件
  - 定义交通信号灯的相位和时长
  
- **`hangzhou_4x4_converted.net.xml`** - 完整路网文件 ⭐
  - 整合了上述所有文件的完整SUMO路网

### 2. 交通流文件

- **`hangzhou_4x4_converted.rou.xml`** - 车辆路由文件 ⭐
  - 定义所有车辆的出发时间和行驶路线

### 3. 配置文件

- **`hangzhou_4x4_converted.sumocfg`** - SUMO配置文件 ⭐
  - SUMO仿真的主配置文件
  - 仿真时长: 0-3600秒（1小时）

## 如何使用

### 方法1: 使用SUMO GUI（图形界面）

```bash
cd /home/sjx/jx/LibSignal/data/raw_data/hangzhou_4x4_gudang_18041610_1h
sumo-gui -c hangzhou_4x4_converted.sumocfg
```

### 方法2: 使用SUMO命令行（无界面）

```bash
cd /home/sjx/jx/LibSignal/data/raw_data/hangzhou_4x4_gudang_18041610_1h
sumo -c hangzhou_4x4_converted.sumocfg
```

### 方法3: 在LibSignal中使用

在LibSignal的配置文件中引用这些SUMO文件：

```json
{
  "roadnetFile": "data/raw_data/hangzhou_4x4_gudang_18041610_1h/hangzhou_4x4_converted.net.xml",
  "flowFile": "data/raw_data/hangzhou_4x4_gudang_18041610_1h/hangzhou_4x4_converted.rou.xml",
  "combined_file": "data/raw_data/hangzhou_4x4_gudang_18041610_1h/hangzhou_4x4_converted.sumocfg"
}
```

## 路网信息

- **路网规模**: 4×4网格（16个交叉路口）
- **位置**: 杭州古荡地区
- **数据时间**: 2018年04月16日10时
- **时长**: 1小时
- **交叉路口**: 16个信号灯控制的路口

## 转换工具

转换使用LibSignal提供的转换器：
- **转换脚本**: `/home/sjx/jx/LibSignal/convert_hangzhou_4x4.py`
- **转换器源码**: `/home/sjx/jx/LibSignal/common/converter.py`

## 转换其他数据集

如果你想转换其他CityFlow数据集，可以使用以下命令：

```bash
cd /home/sjx/jx/LibSignal
python common/converter.py \
  --typ c2s \
  --or_cityflownet "路径/到/roadnet.json" \
  --sumonet "路径/到/输出.net.xml" \
  --or_cityflowtraffic "路径/到/flow.json" \
  --sumotraffic "路径/到/输出.rou.xml"
```

或者修改 `convert_hangzhou_4x4.py` 脚本中的路径。

## 注意事项

1. 确保已安装SUMO及其依赖
2. 确保已设置SUMO_HOME环境变量
3. 在traffic虚拟环境中运行转换脚本
4. 转换后的文件保持了原始CityFlow数据的交通流特征

---

**转换日期**: 2026-01-04  
**LibSignal版本**: Latest



