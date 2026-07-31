/**
 * SUMO交通监控Dashboard - 可视化引擎
 * 
 * 功能：
 * 1. 渲染地图（道路、节点、路口）
 * 2. 支持拖动、缩放
 * 3. 鼠标悬停显示简略信息
 * 4. 点击路口触发详情面板
 * 5. 显示拥堵热力图
 */

class MapVisualization {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) {
            throw new Error(`Canvas元素未找到: ${canvasId}`);
        }
        
        this.ctx = this.canvas.getContext('2d');
        
        // 视图控制
        this.viewX = 0;
        this.viewY = 0;
        this.scale = 1.0;
        this.minScale = 0.1;
        this.maxScale = 10.0;
        
        // 交互状态
        this.isDragging = false;
        this.lastMouseX = 0;
        this.lastMouseY = 0;
        
        // 显示配置
        this.displayConfig = {
            showEdges: true,
            showNodes: true,
            showJunctions: true,
            showLabels: false,
            showCongestion: true,
            lineWidth: 1.8,
            nodeSize: 6,
            enableLaneFilter: true,
            minLanes: 2
        };
        
        // 颜色配置
        this.colors = {
            background: '#f5f9fa',
            edge: '#8da2a8',
            node: '#6f858b',
            junction: '#0b9488',
            junctionTrafficLight: '#0b9488',
            junctionNormal: '#71878d',
            text: '#415d63',
            selected: '#705cc9',
            hovered: '#d98220',
            // 拥堵级别颜色
            congestion: {
                free: '#17875f',      // 0-0.2: 畅通
                slow: '#6d9c2c',      // 0.2-0.4: 缓慢
                moderate: '#c79a16',  // 0.4-0.6: 拥堵
                heavy: '#d87820',     // 0.6-0.8: 严重拥堵
                jammed: '#d34a4a'     // 0.8-1.0: 瘫痪
            }
        };
        
        // 数据
        this.networkData = null;
        this.junctionSummaries = {};  // junction_id -> summary
        
        // 拥堵扩散数据（持久化，避免闪烁）
        this.edgeCongestion = {};
        this.nodeCongestion = {};
        
        // 选中和悬停
        this.selectedJunction = null;
        this.hoveredElement = null;
        
        // 事件回调
        this.onJunctionClick = null;
        
        this.setupCanvas();
        this.setupEventListeners();
    }
    
    setupCanvas() {
        const resizeCanvas = () => {
            const rect = this.canvas.parentElement.getBoundingClientRect();
            this.canvas.width = rect.width;
            this.canvas.height = rect.height;
            this.render();
        };
        
        resizeCanvas();
        window.addEventListener('resize', resizeCanvas);
    }
    
    setupEventListeners() {
        this.canvas.addEventListener('mousedown', this.onMouseDown.bind(this));
        this.canvas.addEventListener('mousemove', this.onMouseMove.bind(this));
        this.canvas.addEventListener('mouseup', this.onMouseUp.bind(this));
        this.canvas.addEventListener('wheel', this.onWheel.bind(this));
        this.canvas.addEventListener('click', this.onClick.bind(this));
        this.canvas.addEventListener('contextmenu', (e) => e.preventDefault());
    }
    
    // ========== 鼠标事件处理 ==========
    
    onMouseDown(event) {
        const rect = this.canvas.getBoundingClientRect();
        this.lastMouseX = event.clientX - rect.left;
        this.lastMouseY = event.clientY - rect.top;
        
        if (event.button === 0) {
            this.isDragging = true;
        }
    }
    
    onMouseMove(event) {
        const rect = this.canvas.getBoundingClientRect();
        const mouseX = event.clientX - rect.left;
        const mouseY = event.clientY - rect.top;
        
        if (this.isDragging) {
            const deltaX = mouseX - this.lastMouseX;
            const deltaY = mouseY - this.lastMouseY;
            
            this.viewX += deltaX;
            this.viewY += deltaY;
            
            this.render();
        } else {
            this.checkHover(mouseX, mouseY);
        }
        
        this.lastMouseX = mouseX;
        this.lastMouseY = mouseY;
    }
    
    onMouseUp(event) {
        if (event.button === 0) {
            this.isDragging = false;
        }
    }
    
    onWheel(event) {
        event.preventDefault();
        
        const rect = this.canvas.getBoundingClientRect();
        const mouseX = event.clientX - rect.left;
        const mouseY = event.clientY - rect.top;
        
        const scaleFactor = event.deltaY > 0 ? 0.9 : 1.1;
        const newScale = Math.max(this.minScale, Math.min(this.maxScale, this.scale * scaleFactor));
        
        if (newScale !== this.scale) {
            const worldX = (mouseX - this.viewX) / this.scale;
            const worldY = (mouseY - this.viewY) / this.scale;
            
            this.scale = newScale;
            
            this.viewX = mouseX - worldX * this.scale;
            this.viewY = mouseY - worldY * this.scale;
            
            this.updateScaleIndicator();
            this.render();
        }
    }
    
    onClick(event) {
        const rect = this.canvas.getBoundingClientRect();
        const mouseX = event.clientX - rect.left;
        const mouseY = event.clientY - rect.top;
        
        const element = this.getElementAtPosition(mouseX, mouseY);
        
        if (element && element.type === 'junction') {
            this.selectedJunction = element.id;
            
            // 触发回调
            if (this.onJunctionClick) {
                this.onJunctionClick(element.id, element.data);
            }
            
            this.render();
        } else {
            this.selectedJunction = null;
            this.render();
        }
    }
    
    checkHover(mouseX, mouseY) {
        const element = this.getElementAtPosition(mouseX, mouseY);
        
        if (element !== this.hoveredElement) {
            this.hoveredElement = element;
            
            if (element) {
                this.showTooltip(element, mouseX, mouseY);
            } else {
                this.hideTooltip();
            }
            
            this.render();
        }
    }
    
    // ========== 元素检测 ==========
    
    getElementAtPosition(x, y) {
        if (!this.networkData) return null;
        
        const worldX = (x - this.viewX) / this.scale;
        const worldY = (y - this.viewY) / this.scale;
        
        // 优先检测路口
        if (this.displayConfig.showJunctions && this.networkData.inter) {
            for (const [id, inter] of Object.entries(this.networkData.inter)) {
                if (typeof inter.x === 'number' && typeof inter.y === 'number') {
                    const dx = worldX - inter.x;
                    const dy = worldY - inter.y;
                    const distance = Math.sqrt(dx * dx + dy * dy);
                    
                    if (distance <= this.displayConfig.nodeSize + 3) {
                        const summary = this.junctionSummaries[id] || {};
                        return { 
                            type: 'junction', 
                            id, 
                            data: { ...inter, ...summary }
                        };
                    }
                }
            }
        }
        
        // 检测节点
        if (this.displayConfig.showNodes && this.networkData.node) {
            for (const [id, node] of Object.entries(this.networkData.node)) {
                if (typeof node.x === 'number' && typeof node.y === 'number') {
                    // 跳过已经作为路口的节点
                    if (this.networkData.inter && this.networkData.inter[id]) continue;
                    
                    const dx = worldX - node.x;
                    const dy = worldY - node.y;
                    const distance = Math.sqrt(dx * dx + dy * dy);
                    
                    if (distance <= this.displayConfig.nodeSize) {
                        return { type: 'node', id, data: node };
                    }
                }
            }
        }
        
        return null;
    }
    
    // ========== 工具提示 ==========
    
    showTooltip(element, x, y) {
        const tooltip = document.getElementById('tooltip');
        let content = '';
        
        if (element.type === 'junction') {
            const data = element.data;
            
            content = `
                <strong>路口: ${element.id}</strong><br>
                类型: ${data.junction_type === 'traffic_light' ? '🚦 信号灯' : '⚠️ 优先通行'}<br>
                <em style="color: #888;">点击查看详情</em>
            `;
        } else if (element.type === 'node') {
            content = `
                <strong>节点: ${element.id}</strong><br>
                位置: (${element.data.x?.toFixed(1)}, ${element.data.y?.toFixed(1)})
            `;
        }
        
        tooltip.innerHTML = content;
        tooltip.style.left = (x + 15) + 'px';
        tooltip.style.top = (y - 10) + 'px';
        tooltip.style.display = 'block';
    }
    
    hideTooltip() {
        document.getElementById('tooltip').style.display = 'none';
    }
    
    getCongestionText(level) {
        if (level < 0.2) return '畅通';
        if (level < 0.4) return '缓慢';
        if (level < 0.6) return '拥堵';
        if (level < 0.8) return '严重';
        return '瘫痪';
    }
    
    getCongestionColor(level) {
        // 调低阈值，让轻微拥堵更早显色。
        if (level < 0.05) return this.colors.congestion.free;
        if (level < 0.15) return this.colors.congestion.slow;
        if (level < 0.3) return this.colors.congestion.moderate;
        if (level < 0.5) return this.colors.congestion.heavy;
        return this.colors.congestion.jammed;
    }
    
    // ========== 渲染方法 ==========
    
    render() {
        // 清空画布
        this.ctx.fillStyle = this.colors.background;
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
        
        if (!this.networkData) {
            this.drawWelcomeMessage();
            return;
        }
        
        this.ctx.save();
        this.ctx.translate(this.viewX, this.viewY);
        this.ctx.scale(this.scale, this.scale);
        
        // 渲染顺序：边 -> 节点 -> 路口 -> 标签
        if (this.displayConfig.showEdges) {
            this.drawEdges();
        }
        
        if (this.displayConfig.showNodes) {
            this.drawNodes();
        }
        
        if (this.displayConfig.showJunctions) {
            this.drawJunctions();
        }
        
        if (this.displayConfig.showLabels && this.scale > 0.8) {
            this.drawLabels();
        }
        
        this.ctx.restore();
    }
    
    drawWelcomeMessage() {
        this.ctx.fillStyle = this.colors.text;
        this.ctx.font = '24px Arial';
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'middle';
        
        const x = this.canvas.width / 2;
        const y = this.canvas.height / 2;
        
        this.ctx.fillText('正在加载地图数据...', x, y);
    }
    
    drawEdges() {
        if (!this.networkData.edge) return;
        
        // 线宽保持为屏幕像素，不随“适应全图”的低缩放比例变得不可见。
        this.ctx.lineWidth = this.displayConfig.lineWidth / Math.max(this.scale, 0.01);
        this.ctx.lineCap = 'round';
        
        let renderedCount = 0;
        let filteredCount = 0;
        
        for (const [id, edge] of Object.entries(this.networkData.edge)) {
            if (!edge.incnode_coord || !edge.outnode_coord) continue;
            
            // 车道数过滤
            if (this.displayConfig.enableLaneFilter && edge.nlanes) {
                if (edge.nlanes < this.displayConfig.minLanes) {
                    filteredCount++;
                    continue;
                }
            }
            
            const [x1, y1] = edge.incnode_coord;
            const [x2, y2] = edge.outnode_coord;
            
            // 计算边的拥堵颜色（使用扩散算法结果）
            const edgeColor = this.getEdgeCongestionColor(id, edge.incnode, edge.outnode);
            
            this.ctx.strokeStyle = edgeColor;
            this.ctx.beginPath();
            this.ctx.moveTo(x1, y1);
            this.ctx.lineTo(x2, y2);
            this.ctx.stroke();
            
            renderedCount++;
        }
    }
    
    /**
     * 根据边ID和两端节点计算边的拥堵颜色
     * 仅使用扩散算法的结果，不使用静态junction数据
     */
    getEdgeCongestionColor(edgeId, incnode, outnode) {
        // 如果未启用拥堵显示，返回默认颜色
        if (!this.displayConfig.showCongestion) {
            return this.colors.edge;
        }
        
        // 仅使用扩散算法计算的边拥堵度
        if (this.edgeCongestion && this.edgeCongestion[edgeId] !== undefined) {
            return this.getCongestionColor(this.edgeCongestion[edgeId]);
        }
        
        // 没有扩散数据时，按“畅通”处理，而不是保留灰色。
        return this.getCongestionColor(0);
    }
    
    drawNodes() {
        if (!this.networkData.node) return;
        
        for (const [id, node] of Object.entries(this.networkData.node)) {
            // 跳过路口节点
            if (this.networkData.inter && this.networkData.inter[id]) continue;
            
            if (typeof node.x !== 'number' || typeof node.y !== 'number') continue;
            
            // 获取节点的拥堵度（如果有扩散数据）
            let nodeCongestion = null;
            if (this.displayConfig.showCongestion && this.nodeCongestion && 
                this.nodeCongestion[id] !== undefined) {
                nodeCongestion = this.nodeCongestion[id];
            }
            
            // 没有节点级拥堵数据时，也按畅通(0.0)渲染为绿色。
            if (this.displayConfig.showCongestion) {
                this.ctx.fillStyle = this.getCongestionColor(nodeCongestion ?? 0);
            } else {
                this.ctx.fillStyle = this.colors.node;
            }
            this.ctx.beginPath();
            const radius = 1.15 / Math.max(this.scale, 0.01);
            this.ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
            this.ctx.fill();
        }
    }
    
    drawJunctions() {
        if (!this.networkData.inter) return;
        
        for (const [id, inter] of Object.entries(this.networkData.inter)) {
            if (typeof inter.x !== 'number' || typeof inter.y !== 'number') continue;
            
            const summary = this.junctionSummaries[id] || {};
            const isTrafficLight = summary.junction_type === 'traffic_light';
            const hasCongestionData = summary.congestion_level !== undefined && summary.congestion_level !== null;
            const congestionLevel = hasCongestionData ? summary.congestion_level : 0;
            
            const visualScale = Math.max(this.scale, 0.01);
            let radius = 4 / visualScale;
            let color = isTrafficLight ? this.colors.junctionTrafficLight : this.colors.junctionNormal;
            
            // 高亮选中和悬停
            if (this.selectedJunction === id) {
                color = this.colors.selected;
                radius += 3 / visualScale;
            } else if (this.hoveredElement?.type === 'junction' && this.hoveredElement.id === id) {
                color = this.colors.hovered;
                radius += 2 / visualScale;
            } else if (this.displayConfig.showCongestion) {
                // 无数据时视为畅通(0.0)，直接渲染为绿色而不是灰色。
                color = this.getCongestionColor(congestionLevel);
            }
            
            // 绘制路口
            this.ctx.fillStyle = color;
            this.ctx.beginPath();
            this.ctx.arc(inter.x, inter.y, radius, 0, 2 * Math.PI);
            this.ctx.fill();
            
            // 绘制边框
            this.ctx.strokeStyle = '#000';
            this.ctx.lineWidth = 1 / visualScale;
            this.ctx.stroke();
            
            // 如果是信号灯路口，绘制额外标记
            if (isTrafficLight) {
                this.ctx.strokeStyle = '#fff';
                this.ctx.lineWidth = 1.5 / visualScale;
                this.ctx.beginPath();
                this.ctx.arc(inter.x, inter.y, radius + 2 / visualScale, 0, 2 * Math.PI);
                this.ctx.stroke();
            }
        }
    }
    
    drawLabels() {
        if (!this.networkData.inter) return;
        
        this.ctx.fillStyle = this.colors.text;
        this.ctx.font = '11px Arial';
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'top';
        
        for (const [id, inter] of Object.entries(this.networkData.inter)) {
            if (typeof inter.x !== 'number' || typeof inter.y !== 'number') continue;
            this.ctx.fillText(id, inter.x, inter.y + this.displayConfig.nodeSize + 5);
        }
    }
    
    // ========== 公共方法 ==========
    
    loadNetworkData(data) {
        this.networkData = data;
        this.fitToNetwork();
        this.render();
    }
    
    updateJunctionSummaries(summaries) {
        // summaries 是数组，转换为字典
        if (Array.isArray(summaries)) {
            this.junctionSummaries = {};
            for (const summary of summaries) {
                this.junctionSummaries[summary.junction_id] = summary;
            }
        } else {
            this.junctionSummaries = summaries;
        }
        
        // 静态数据加载时不进行扩散染色
        // 扩散算法仅在实时更新时使用（updateCongestion调用）
        
        this.render();
    }
    
    /**
     * 更新拥堵热力图数据
     * @param {Object} congestionData - 格式: {junction_id: congestion_level}
     */
    updateCongestion(congestionData) {
        if (!congestionData) return;
        
        // 更新路口拥堵数据
        for (const [junctionId, congestionLevel] of Object.entries(congestionData)) {
            if (!this.junctionSummaries[junctionId]) {
                this.junctionSummaries[junctionId] = {};
            }
            this.junctionSummaries[junctionId].congestion_level = congestionLevel;
        }
        
        // 应用拥堵扩散算法
        this.diffuseCongestion(congestionData);
        
        // 重新渲染
        this.render();
    }
    
    /**
     * 拥堵扩散算法
     * 从信号灯路口向周边普通节点和边扩散拥堵度
     */
    diffuseCongestion(congestionData) {
        if (!this.networkData || !this.networkData.edge || !this.networkData.node) {
            console.warn('[Diffusion] 缺少网络数据');
            return;
        }
        
        // 先对现有拥堵度进行时间衰减（避免闪烁）
        const TIME_DECAY = 0.95; // 每次更新保留95%的拥堵度
        for (const edgeId in this.edgeCongestion) {
            this.edgeCongestion[edgeId] *= TIME_DECAY;
            // 如果拥堵度太低，删除以节省内存
            if (this.edgeCongestion[edgeId] < 0.01) {
                delete this.edgeCongestion[edgeId];
            }
        }
        for (const nodeId in this.nodeCongestion) {
            this.nodeCongestion[nodeId] *= TIME_DECAY;
            if (this.nodeCongestion[nodeId] < 0.01) {
                delete this.nodeCongestion[nodeId];
            }
        }
        
        // 衰减参数：每100米衰减的比例（降低衰减率以增加扩散范围）
        const DECAY_PER_100M = 0.1; // 从0.2降低到0.1，衰减更慢
        const MAX_DIFFUSION_DISTANCE = 2000; // 最大扩散距离（米），从500增加到2000
        
        // 建立节点到边的映射
        const nodeToEdges = this.buildNodeToEdgesMap();
        
        // 注释掉详细日志，只在出错时输出
        // const junctionCount = Object.keys(congestionData).length;
        // const edgeCount = Object.keys(nodeToEdges).length;
        // console.log(`[Diffusion] 开始扩散: ${junctionCount} 个路口, ${edgeCount} 个节点连接`);
        
        // 使用BFS从每个信号灯路口扩散
        let junctionProcessed = 0;
        for (const [junctionId, congestionLevel] of Object.entries(congestionData)) {
            if (congestionLevel === undefined || congestionLevel === null) continue;
            
            // 获取路口连接的所有边
            const junction = this.networkData.inter ? this.networkData.inter[junctionId] : null;
            if (!junction) {
                console.warn(`[Diffusion] 路口 ${junctionId} 在网络数据中不存在`);
                continue;
            }
            
            // 从路口的所有出边开始扩散
            const queue = [];
            const visited = new Set();
            
            // 添加所有出边的终点节点作为起点
            // 将Set转换为数组
            const outgoingEdges = Array.from(junction.outgoing || []);
            const incomingEdges = Array.from(junction.incoming || []);
            
            // if (junctionProcessed === 0) {
            //     console.log(`[Diffusion] 路口 ${junctionId}: ${outgoingEdges.length} 出边, ${incomingEdges.length} 入边`);
            // }
            
            for (const edgeId of outgoingEdges) {
                const edge = this.networkData.edge[edgeId];
                if (!edge) continue;
                
                const nextNode = edge.outnode || edge.tonode_id || edge.to;
                if (!nextNode || visited.has(nextNode)) continue;
                
                visited.add(nextNode);
                queue.push({
                    nodeId: nextNode,
                    congestion: congestionLevel,
                    distance: 0
                });
            }
            
            // 同样处理入边
            for (const edgeId of incomingEdges) {
                const edge = this.networkData.edge[edgeId];
                if (!edge) continue;
                
                const nextNode = edge.incnode || edge.fromnode_id || edge.from;
                if (!nextNode || visited.has(nextNode)) continue;
                
                visited.add(nextNode);
                queue.push({
                    nodeId: nextNode,
                    congestion: congestionLevel,
                    distance: 0
                });
            }
            
            // 调试日志（已注释）
            // if (junctionProcessed === 0 && queue.length > 0) {
            //     console.log(`[Diffusion] 第一个路口初始队列: ${queue.length} 个节点, 拥堵度: ${congestionLevel}`);
            // }
            
            junctionProcessed++;
            
            let loopCount = 0;
            while (queue.length > 0) {
                const current = queue.shift();
                loopCount++;
                
                // 距离过远，停止扩散
                if (current.distance > MAX_DIFFUSION_DISTANCE) continue;
                
                // 更新当前节点的拥堵度（取最大值）
                if (!this.nodeCongestion[current.nodeId] || 
                    this.nodeCongestion[current.nodeId] < current.congestion) {
                    this.nodeCongestion[current.nodeId] = current.congestion;
                }
                
                // 扩散到相邻的边和节点
                const adjacentEdges = nodeToEdges[current.nodeId] || [];
                
                // if (junctionProcessed === 1 && loopCount === 1) {
                //     console.log(`[Diffusion] 第一个节点 ${current.nodeId} 有 ${adjacentEdges.length} 条相邻边`);
                //     if (adjacentEdges.length > 0) {
                //         console.log(`[Diffusion] 第一条边ID: ${adjacentEdges[0].edgeId}, 目标节点: ${adjacentEdges[0].toNode}`);
                //     }
                // }
                
                for (const edgeInfo of adjacentEdges) {
                    const edge = this.networkData.edge[edgeInfo.edgeId];
                    if (!edge) continue;
                    
                    // 计算边的长度
                    const edgeLength = edge.length || 100;
                    
                    // 计算衰减后的拥堵度
                    // 使用更慢的指数衰减，让拥堵度传播更远
                    const decayFactor = Math.exp(-edgeLength / 800); // 衰减因子，800米处衰减到37%（原500米）
                    const newCongestion = current.congestion * decayFactor;
                    
                    // 如果拥堵度降到0或负数，停止扩散
                    if (newCongestion <= 0) continue;
                    
                    // 更新边的拥堵度（取最大值）
                    if (!this.edgeCongestion[edgeInfo.edgeId] || 
                        this.edgeCongestion[edgeInfo.edgeId] < newCongestion) {
                        this.edgeCongestion[edgeInfo.edgeId] = newCongestion;
                    }
                    
                    // 扩散到下一个节点
                    const nextNodeId = edgeInfo.toNode;
                    if (!visited.has(nextNodeId)) {
                        visited.add(nextNodeId);
                        queue.push({
                            nodeId: nextNodeId,
                            congestion: newCongestion,
                            distance: current.distance + edgeLength
                        });
                    }
                }
            }
        }
        
        // 输出扩散结果统计（仅首次或有问题时）
        // const edgesCovered = Object.keys(this.edgeCongestion).length;
        // const nodesCovered = Object.keys(this.nodeCongestion).length;
        // console.log(`[Diffusion] 扩散完成: ${edgesCovered} 条边, ${nodesCovered} 个节点被覆盖`);
    }
    
    /**
     * 建立节点到边的映射关系
     */
    buildNodeToEdgesMap() {
        const nodeToEdges = {};
        
        if (!this.networkData.edge) return nodeToEdges;
        
        for (const [edgeId, edge] of Object.entries(this.networkData.edge)) {
            // 兼容不同的字段名
            const fromNode = edge.incnode || edge.fromnode_id || edge.from;
            const toNode = edge.outnode || edge.tonode_id || edge.to;
            
            if (!fromNode || !toNode) continue;
            
            // 从fromNode出发
            if (!nodeToEdges[fromNode]) {
                nodeToEdges[fromNode] = [];
            }
            nodeToEdges[fromNode].push({
                edgeId: edgeId,
                toNode: toNode,
                direction: 'out'
            });
            
            // 到达toNode（考虑双向道路）
            if (!nodeToEdges[toNode]) {
                nodeToEdges[toNode] = [];
            }
            nodeToEdges[toNode].push({
                edgeId: edgeId,
                toNode: fromNode,
                direction: 'in'
            });
        }
        
        return nodeToEdges;
    }
    
    updateDisplayConfig(config) {
        Object.assign(this.displayConfig, config);
        this.render();
    }
    
    fitToNetwork() {
        if (!this.networkData) return;
        
        let minX = Infinity, minY = Infinity;
        let maxX = -Infinity, maxY = -Infinity;
        
        // 计算边界
        if (this.networkData.edge) {
            for (const edge of Object.values(this.networkData.edge)) {
                if (edge.incnode_coord) {
                    const [x, y] = edge.incnode_coord;
                    minX = Math.min(minX, x);
                    minY = Math.min(minY, y);
                    maxX = Math.max(maxX, x);
                    maxY = Math.max(maxY, y);
                }
                if (edge.outnode_coord) {
                    const [x, y] = edge.outnode_coord;
                    minX = Math.min(minX, x);
                    minY = Math.min(minY, y);
                    maxX = Math.max(maxX, x);
                    maxY = Math.max(maxY, y);
                }
            }
        }
        
        if (minX === Infinity) return;
        
        const width = maxX - minX;
        const height = maxY - minY;
        const padding = 50;
        
        const scaleX = (this.canvas.width - padding * 2) / width;
        const scaleY = (this.canvas.height - padding * 2) / height;
        
        this.scale = Math.min(scaleX, scaleY, this.maxScale);
        
        const centerX = (minX + maxX) / 2;
        const centerY = (minY + maxY) / 2;
        
        this.viewX = this.canvas.width / 2 - centerX * this.scale;
        this.viewY = this.canvas.height / 2 - centerY * this.scale;
        
        this.updateScaleIndicator();
    }
    
    zoomIn() {
        const centerX = this.canvas.width / 2;
        const centerY = this.canvas.height / 2;
        this.zoomAt(centerX, centerY, 1.2);
    }
    
    zoomOut() {
        const centerX = this.canvas.width / 2;
        const centerY = this.canvas.height / 2;
        this.zoomAt(centerX, centerY, 0.8);
    }
    
    zoomAt(x, y, factor) {
        const newScale = Math.max(this.minScale, Math.min(this.maxScale, this.scale * factor));
        
        if (newScale !== this.scale) {
            const worldX = (x - this.viewX) / this.scale;
            const worldY = (y - this.viewY) / this.scale;
            
            this.scale = newScale;
            
            this.viewX = x - worldX * this.scale;
            this.viewY = y - worldY * this.scale;
            
            this.updateScaleIndicator();
            this.render();
        }
    }
    
    resetView() {
        this.fitToNetwork();
        this.render();
    }
    
    updateScaleIndicator() {
        const indicator = document.getElementById('scale-indicator');
        if (indicator) {
            indicator.textContent = `缩放: ${Math.round(this.scale * 100)}%`;
        }
    }
}
