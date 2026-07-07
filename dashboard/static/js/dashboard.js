/**
 * SUMO交通监控Dashboard - 主控制脚本
 * 
 * 统一管理前端组件和API通信
 */

class Dashboard {
    constructor() {
        this.map = null;
        this.panel = null;
        this.apiBaseUrl = '/api';
        
        // 工具栏状态
        this.sidebarCollapsed = false;
        this.currentTool = null;
        
        // 配置（将从服务器加载）
        this.config = {
            dashboard: {
                title: '交通信控系统',
                auto_refresh: false,
                refresh_interval: 5000,
                default_view: {
                    showEdges: true,
                    showNodes: true,
                    showJunctions: true,
                    showLabels: false,
                    showCongestion: true,
                    lineWidth: 2,
                    nodeSize: 6,
                    enableLaneFilter: true,
                    minLanes: 2
                }
            }
        };
        
        // 数据刷新配置
        this.autoRefresh = false;
        this.refreshInterval = 5000; // 5秒
        this.refreshTimer = null;
        
        // 网络数据
        this.networkData = null;
        this.junctionSummaries = [];
        
        // 实时统计数据
        this.realtimeStats = null;
        this.realtimeTimer = null;
        this.latestSimulation = null;
        
        this.init();
    }
    
    /**
     * 初始化Dashboard
     */
    async init() {
        try {
            console.log('[Dashboard] 正在初始化...');
            
            // 1. 加载配置
            await this.loadConfig();
            
            // 2. 应用配置到页面
            this.applyConfig();
            
            // 3. 初始化地图可视化
            this.map = new MapVisualization('map-canvas');
            this.map.onJunctionClick = (junctionId, data) => {
                this.showJunctionDetail(junctionId);
            };
            
            // 应用默认视图配置
            if (this.config.dashboard.default_view) {
                this.map.updateDisplayConfig(this.config.dashboard.default_view);
                this.updateDisplayControls();
            }
            
            // 4. 初始化路口详情面板
            this.panel = new JunctionPanel('detail-panel');
            
            // 5. 加载网络数据
            await this.loadNetworkData();
            
            // 6. 加载仿真预设
            await this.loadSimulationPresets();
            
            // 7. 初始化实时更新（监听仿真状态）
            this.startRealtimeUpdates();
            
            console.log('[Dashboard] 初始化完成');
            this.updateConnectionStatus(true);
            
        } catch (error) {
            console.error('[Dashboard] 初始化失败:', error);
            this.showError('Dashboard初始化失败: ' + error.message);
            this.updateConnectionStatus(false);
        }
    }
    
    /**
     * 加载配置
     */
    async loadConfig() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/config`);
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.config) {
                    this.config = data.config;
                    console.log('[Dashboard] 配置加载成功:', this.config);
                }
            }
        } catch (error) {
            console.warn('[Dashboard] 配置加载失败，使用默认配置:', error);
        }
    }
    
    /**
     * 应用配置到页面
     */
    applyConfig() {
        // 更新页面标题
        if (this.config.dashboard.title) {
            document.title = this.config.dashboard.title;
            const titleElements = document.querySelectorAll('.toolbar-title, .header h1');
            titleElements.forEach(el => {
                if (el) el.textContent = this.config.dashboard.title;
            });
        }
    }
    
    /**
     * 更新显示控件的值
     */
    updateDisplayControls() {
        const view = this.config.dashboard.default_view;
        if (!view) return;
        
        if (view.showEdges !== undefined) {
            const el = document.getElementById('show-edges');
            if (el) el.checked = view.showEdges;
        }
        if (view.showNodes !== undefined) {
            const el = document.getElementById('show-nodes');
            if (el) el.checked = view.showNodes;
        }
        if (view.showJunctions !== undefined) {
            const el = document.getElementById('show-junctions');
            if (el) el.checked = view.showJunctions;
        }
        if (view.showLabels !== undefined) {
            const el = document.getElementById('show-labels');
            if (el) el.checked = view.showLabels;
        }
        if (view.showCongestion !== undefined) {
            const el = document.getElementById('show-congestion');
            if (el) el.checked = view.showCongestion;
        }
        if (view.lineWidth !== undefined) {
            const el = document.getElementById('line-width');
            if (el) {
                el.value = view.lineWidth;
                document.getElementById('line-width-value').textContent = view.lineWidth;
            }
        }
        if (view.nodeSize !== undefined) {
            const el = document.getElementById('node-size');
            if (el) {
                el.value = view.nodeSize;
                document.getElementById('node-size-value').textContent = view.nodeSize;
            }
        }
        if (view.enableLaneFilter !== undefined) {
            const el = document.getElementById('enable-lane-filter');
            if (el) el.checked = view.enableLaneFilter;
        }
        if (view.minLanes !== undefined) {
            const el = document.getElementById('min-lanes');
            if (el) {
                el.value = view.minLanes;
                document.getElementById('min-lanes-value').textContent = view.minLanes;
            }
        }
    }
    
    /**
     * 加载网络数据
     */
    async loadNetworkData() {
        this.showLoading(true);
        
        try {
            const response = await fetch(`${this.apiBaseUrl}/network`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.error) {
                throw new Error(data.error);
            }
            
            this.networkData = data.network_data;
            
            // 加载到地图
            this.map.loadNetworkData(this.networkData);
            
            console.log('[Dashboard] 网络数据加载成功');
            this.updateConnectionStatus(true);
            
            // 加载路口摘要
            await this.refreshJunctionSummaries();
            
        } catch (error) {
            console.error('[Dashboard] 网络数据加载失败:', error);
            this.showError('网络数据加载失败: ' + error.message);
            this.updateConnectionStatus(false);
            throw error;
        } finally {
            this.showLoading(false);
        }
    }
    
    /**
     * 刷新路口摘要信息
     */
    async refreshJunctionSummaries() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/junctions/summary`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.error) {
                throw new Error(data.error);
            }
            
            this.junctionSummaries = data.summaries;
            
            // 更新地图显示
            this.map.updateJunctionSummaries(this.junctionSummaries);
            this.updateInferenceHud();
            
            console.log(`[Dashboard] 刷新了 ${this.junctionSummaries.length} 个路口的摘要`);
            
        } catch (error) {
            console.error('[Dashboard] 刷新路口摘要失败:', error);
            // 不抛出错误，因为这是后台刷新
        }
    }
    
    /**
     * 显示路口详情
     */
    async showJunctionDetail(junctionId) {
        try {
            const junction = await this.fetchJunctionState(junctionId);
            this.panel.open(junctionId, junction);
            console.log(`[Dashboard] 显示路口详情: ${junctionId}`);
            
        } catch (error) {
            console.error('[Dashboard] 加载路口详情失败:', error);
            this.showError('加载路口详情失败: ' + error.message);
        }
    }
    
    /**
     * 获取路口详情（用于实时更新）
     */
    async fetchJunctionDetail(junctionId) {
        try {
            const junction = await this.fetchJunctionState(junctionId);
            if (this.panel && this.panel.isOpen() && this.panel.getCurrentJunctionId() === junctionId) {
                this.panel.update(junction);
            }
        } catch (error) {
            // 静默失败
            console.debug('[Dashboard] 更新路口详情失败:', error.message);
        }
    }
    
    /**
     * 关闭详情面板
     */
    closeDetailPanel() {
        this.panel.close();
        this.map.selectedJunction = null;
        this.map.render();
    }
    
    /**
     * 刷新数据
     */
    async refreshData() {
        console.log('[Dashboard] 手动刷新数据');
        await this.refreshJunctionSummaries();
        
        // 如果详情面板打开，刷新详情
        if (this.panel.currentJunctionId) {
            await this.showJunctionDetail(this.panel.currentJunctionId);
        }
        
        this.showMessage('数据已刷新', 'success');
    }
    
    /**
     * 启动自动刷新
     */
    startAutoRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
        }
        
        this.autoRefresh = true;
        this.refreshTimer = setInterval(() => {
            this.refreshData();
        }, this.refreshInterval);
        
        console.log(`[Dashboard] 自动刷新已启动 (间隔: ${this.refreshInterval}ms)`);
    }
    
    /**
     * 停止自动刷新
     */
    stopAutoRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }
        
        this.autoRefresh = false;
        console.log('[Dashboard] 自动刷新已停止');
    }
    
    /**
     * 更新显示设置
     */
    updateDisplay() {
        const config = {
            showEdges: document.getElementById('show-edges').checked,
            showNodes: document.getElementById('show-nodes').checked,
            showJunctions: document.getElementById('show-junctions').checked,
            showLabels: document.getElementById('show-labels').checked,
            showCongestion: document.getElementById('show-congestion').checked,
            lineWidth: parseInt(document.getElementById('line-width').value),
            nodeSize: parseInt(document.getElementById('node-size').value),
            enableLaneFilter: document.getElementById('enable-lane-filter').checked,
            minLanes: parseInt(document.getElementById('min-lanes').value)
        };
        
        // 更新显示值
        document.getElementById('line-width-value').textContent = config.lineWidth;
        document.getElementById('node-size-value').textContent = config.nodeSize;
        document.getElementById('min-lanes-value').textContent = config.minLanes;
        
        // 应用到地图
        this.map.updateDisplayConfig(config);
    }
    
    /**
     * 切换显示设置面板
     */
    toggleDisplaySettings() {
        const panel = document.getElementById('display-controls');
        if (panel.style.display === 'none' || !panel.style.display) {
            panel.style.display = 'block';
        } else {
            panel.style.display = 'none';
        }
    }
    
    /**
     * 显示连接控制面板
     */
    async showConnectionPanel() {
        document.getElementById('connection-overlay').style.display = 'flex';
        
        // 加载仿真预设信息
        await this.loadSimulationPresets();
    }
    
    /**
     * 加载仿真预设信息
     */
    async loadSimulationPresets() {
        try {
            console.log('[Dashboard] 正在加载仿真预设...');
            const [presetResponse, mapResponse] = await Promise.all([
                fetch('/api/simulation/presets'),
                fetch('/api/maps/list')
            ]);
            
            if (!presetResponse.ok) {
                console.error('[Dashboard] 加载预设失败，HTTP状态:', presetResponse.status);
                return;
            }
            
            const data = await presetResponse.json();
            console.log('[Dashboard] 预设数据:', data);
            
            // 更新当前地图显示
            if (data.current_map) {
                const mapSpan = document.getElementById('current-sim-map');
                if (mapSpan) {
                    mapSpan.textContent = data.current_map;
                    console.log('[Dashboard] 当前地图:', data.current_map);
                }
            }

            if (mapResponse.ok) {
                const mapData = await mapResponse.json();
                if (mapData.success && mapData.maps) {
                    const mapSelect = document.getElementById('sumo-map');
                    if (mapSelect) {
                        mapSelect.innerHTML = '';
                        mapData.maps.forEach(map => {
                            const option = document.createElement('option');
                            option.value = map.id;
                            option.textContent = `${map.name} - ${map.description}`;
                            if (map.id === data.current_map) {
                                option.selected = true;
                            }
                            mapSelect.appendChild(option);
                        });

                        mapSelect.onchange = () => {
                            const mapSpan = document.getElementById('current-sim-map');
                            if (mapSpan) {
                                mapSpan.textContent = mapSelect.value || data.current_map;
                            }
                        };
                    }
                }
            }
            
            // 动态填充预设下拉菜单
            if (data.presets && data.presets.length > 0) {
                const select = document.getElementById('sumo-config');
                if (select) {
                    console.log('[Dashboard] 找到下拉菜单，清空并填充');
                    // 清空现有选项
                    select.innerHTML = '';
                    
                    // 添加新选项
                    data.presets.forEach(preset => {
                        const option = document.createElement('option');
                        option.value = preset.name;
                        option.textContent = preset.description;
                        select.appendChild(option);
                        console.log('[Dashboard] 添加选项:', preset.name, '-', preset.description);
                    });
                    
                    console.log('[Dashboard] 预设加载完成，共', data.presets.length, '个选项');
                } else {
                    console.warn('[Dashboard] 未找到下拉菜单元素 #sumo-config');
                }
            } else {
                console.warn('[Dashboard] 预设数据为空或格式错误');
            }
        } catch (error) {
            console.error('[Dashboard] 加载仿真预设失败:', error);
        }
    }

    /**
     * 隐藏连接控制面板
     */
    hideConnectionPanel() {
        document.getElementById('connection-overlay').style.display = 'none';
    }

    /**
     * 启动SUMO仿真
     */
    async startSumoSimulation() {
        const mapSelect = document.getElementById('sumo-map');
        const configSelect = document.getElementById('sumo-config');
        const simName = mapSelect ? mapSelect.value : undefined;
        const config = configSelect.value;
        const startBtn = document.getElementById('start-sumo-btn');
        
        // 禁用按钮
        startBtn.disabled = true;
        startBtn.textContent = '启动中...';
        
        // 清空日志
        const logContainer = document.getElementById('connection-log');
        logContainer.innerHTML = '';
        
        // 添加日志
        this.addLog('info', `准备启动 ${config} 仿真...`);
        if (simName) {
            this.addLog('info', `使用地图: ${simName}`);
        }
        
        try {
            const response = await fetch('/api/simulation/start', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ config: config, sim_name: simName })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.addLog('success', '仿真启动成功！');
                this.addLog('info', `进程ID: ${data.pid}`);
                this.updateConnectionStatus('running', 'SUMO仿真运行中', `配置: ${config}`);
                
                // 隐藏启动按钮，显示停止按钮
                startBtn.style.display = 'none';
                document.getElementById('stop-sumo-btn').style.display = 'block';
                
                // 开始轮询仿真状态
                this.startSimulationPolling();
            } else {
                this.addLog('error', `启动失败: ${data.message}`);
                startBtn.disabled = false;
                startBtn.textContent = '启动仿真';
            }
        } catch (error) {
            this.addLog('error', `请求失败: ${error.message}`);
            startBtn.disabled = false;
            startBtn.textContent = '启动仿真';
        }
    }

    /**
     * 停止SUMO仿真
     */
    async stopSumoSimulation() {
        this.addLog('info', '正在停止仿真...');
        
        try {
            const response = await fetch('/api/simulation/stop', {
                method: 'POST'
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.addLog('success', '仿真已停止');
                this.updateConnectionStatus('disconnected', '未连接', '等待连接...');
                
                // 停止轮询
                if (this.simulationPolling) {
                    clearInterval(this.simulationPolling);
                    this.simulationPolling = null;
                }
                
                // 恢复按钮状态
                const startBtn = document.getElementById('start-sumo-btn');
                const stopBtn = document.getElementById('stop-sumo-btn');
                startBtn.disabled = false;
                startBtn.textContent = '启动仿真';
                startBtn.style.display = 'block';
                stopBtn.style.display = 'none';
            } else {
                this.addLog('error', `停止失败: ${data.message}`);
            }
        } catch (error) {
            this.addLog('error', `请求失败: ${error.message}`);
        }
    }

    /**
     * 添加日志
     */
    addLog(type, message) {
        const logContainer = document.getElementById('connection-log');
        
        // 移除空日志提示
        const emptyMsg = logContainer.querySelector('.log-empty');
        if (emptyMsg) {
            emptyMsg.remove();
        }
        
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry ${type}`;
        logEntry.textContent = `[${timestamp}] ${message}`;
        
        logContainer.appendChild(logEntry);
        logContainer.scrollTop = logContainer.scrollHeight;
    }

    /**
     * 开始轮询仿真状态
     */
    startSimulationPolling() {
        if (this.simulationPolling) {
            clearInterval(this.simulationPolling);
        }
        
        this.simulationPolling = setInterval(async () => {
            try {
                const response = await fetch('/api/simulation/status');
                const data = await response.json();
                
                if (data.running) {
                    // 更新状态信息
                    if (data.current_time !== undefined) {
                        this.updateConnectionStatus(
                            'running', 
                            'SUMO仿真运行中', 
                            `时间步: ${data.current_time}/${data.total_time || '?'}`
                        );
                    }
                } else {
                    // 仿真已结束
                    this.addLog('info', '仿真已完成');
                    this.updateConnectionStatus('disconnected', '未连接', '等待连接...');
                    
                    clearInterval(this.simulationPolling);
                    this.simulationPolling = null;
                    
                    // 恢复按钮状态
                    const startBtn = document.getElementById('start-sumo-btn');
                    const stopBtn = document.getElementById('stop-sumo-btn');
                    startBtn.disabled = false;
                    startBtn.textContent = '启动仿真';
                    startBtn.style.display = 'block';
                    stopBtn.style.display = 'none';
                }
            } catch (error) {
                console.error('轮询仿真状态失败:', error);
            }
        }, 1000); // 每秒轮询一次
    }
    
    /**
     * 显示统计信息
     */
    showStatistics() {
        const overlay = document.getElementById('stats-overlay');
        
        // 显示浮窗
        overlay.style.display = 'flex';
        
        // 刷新统计面板内容
        this.refreshStatisticsPanel();
    }
    
    /**
     * 隐藏统计信息
     */
    hideStatistics() {
        document.getElementById('stats-overlay').style.display = 'none';
    }
    
    /**
     * 计算网络统计数据
     */
    calculateStatistics() {
        const stats = {
            totalJunctions: this.junctionSummaries.length,
            trafficLightJunctions: 0,
            totalVehicles: 0,
            totalHalting: 0,
            avgCongestion: 0,
            congestedJunctions: 0,
            totalNodes: this.networkData && this.networkData.node ? Object.keys(this.networkData.node).length : 0,
            totalEdges: this.networkData && this.networkData.edge ? Object.keys(this.networkData.edge).length : 0
        };
        
        if (this.junctionSummaries.length > 0) {
            let totalCongestion = 0;
            
            for (const summary of this.junctionSummaries) {
                if (summary.junction_type === 'traffic_light') {
                    stats.trafficLightJunctions++;
                }
                
                stats.totalVehicles += summary.total_vehicles || 0;
                stats.totalHalting += summary.total_halting || 0;
                
                const congestion = summary.congestion_level || 0;
                totalCongestion += congestion;
                
                if (congestion > 0.6) {
                    stats.congestedJunctions++;
                }
            }
            
            stats.avgCongestion = totalCongestion / this.junctionSummaries.length;
        }
        
        return stats;
    }
    
    /**
     * 缩放控制
     */
    zoomIn() {
        if (this.map) {
            this.map.zoomIn();
        }
    }
    
    zoomOut() {
        if (this.map) {
            this.map.zoomOut();
        }
    }
    
    resetView() {
        if (this.map) {
            this.map.resetView();
        }
    }
    
    // ========== UI辅助方法 ==========
    
    showLoading(show) {
        const loading = document.getElementById('loading');
        loading.style.display = show ? 'flex' : 'none';
    }
    
    updateInferenceHud(data = null) {
        const stats = (data && data.statistics) || this.realtimeStats || {};
        const simulation = (data && data.simulation) || this.latestSimulation || {};
        const networkStats = this.calculateStatistics();
        const isRunning = !!simulation.running;

        const totalVehicles = stats.total_vehicles ?? networkStats.totalVehicles ?? 0;
        const totalWaiting = stats.total_waiting ?? networkStats.totalHalting ?? 0;
        const activeAgents = stats.active_junctions ?? networkStats.trafficLightJunctions ?? networkStats.totalJunctions ?? 0;
        const avgSpeed = stats.avg_speed !== undefined ? `${(stats.avg_speed * 3.6).toFixed(1)} km/h` : '0.0 km/h';
        const stepText = simulation.total_steps
            ? `${simulation.current_step || 0}/${simulation.total_steps}`
            : '待机';

        const values = {
            'hud-active-agents': activeAgents,
            'hud-total-vehicles': totalVehicles,
            'hud-total-waiting': totalWaiting,
            'hud-avg-speed': avgSpeed,
            'hud-current-step': stepText,
            'inference-status': isRunning ? '推理运行中' : (networkStats.totalJunctions ? '地图已加载' : '等待数据'),
            'inference-mode': isRunning ? (simulation.config || '在线推理') : 'SUMO / LibSignal'
        };

        Object.entries(values).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = value;
            }
        });

        const hud = document.getElementById('inference-hud');
        if (hud) {
            hud.classList.toggle('running', isRunning);
        }
    }

    updateConnectionStatus(statusValue, label, detail) {
        if (typeof statusValue === 'boolean') {
            statusValue = statusValue ? 'connected' : 'disconnected';
        }

        const statusLabels = {
            running: ['运行中', 'SUMO仿真运行中', '正在接收实时推理数据'],
            connected: ['已连接', '服务已连接', '地图与路口数据已加载'],
            disconnected: ['未连接', '未连接', '等待连接...']
        };
        const [toolbarText, defaultLabel, defaultDetail] = statusLabels[statusValue] || statusLabels.disconnected;
        label = label || defaultLabel;
        detail = detail || defaultDetail;

        const toolbarStatus = document.getElementById('connection-status');
        if (toolbarStatus) {
            toolbarStatus.classList.toggle('connected', statusValue === 'connected');
            toolbarStatus.classList.toggle('running', statusValue === 'running');

            const statusDot = toolbarStatus.querySelector('.status-dot');
            const statusText = toolbarStatus.querySelector('.status-text');
            if (statusDot) {
                statusDot.style.background = statusValue === 'running'
                    ? 'var(--primary-color)'
                    : (statusValue === 'connected' ? 'var(--success-color)' : 'var(--text-secondary)');
            }
            if (statusText) {
                statusText.textContent = toolbarText;
            }
        }

        const connStatusDot = document.getElementById('conn-status-dot');
        const connStatusLabel = document.getElementById('conn-status-label');
        const connStatusDetail = document.getElementById('conn-status-detail');

        if (connStatusDot) {
            connStatusDot.className = 'status-dot-large';
            if (statusValue === 'running') {
                connStatusDot.classList.add('running');
            } else if (statusValue === 'connected') {
                connStatusDot.classList.add('connected');
            }
        }
        if (connStatusLabel) {
            connStatusLabel.textContent = label;
        }
        if (connStatusDetail) {
            connStatusDetail.textContent = detail;
        }

        const inferenceStatus = document.getElementById('inference-status');
        if (inferenceStatus && statusValue === 'running') {
            inferenceStatus.textContent = label;
        }
    }
    
    showMessage(message, type = 'info') {
        console.log(`[Dashboard] ${type.toUpperCase()}: ${message}`);
        
        // 可以添加Toast通知
        // 这里简化为控制台输出
    }
    
    showError(message) {
        console.error(`[Dashboard] ERROR: ${message}`);
        alert('错误: ' + message);
    }
    
    /**
     * 开始实时更新
     */
    startRealtimeUpdates() {
        console.log('[Dashboard] 启动实时更新，间隔: 333ms');
        
        // 每秒更新3次（约333ms一次）
        this.realtimeTimer = setInterval(async () => {
            try {
                const response = await fetch(`${this.apiBaseUrl}/simulation/realtime`);
                if (response.ok) {
                    const data = await response.json();
                    if (data.success) {
                        this.updateRealtimeData(data);
                    }
                }
            } catch (error) {
                // 静默失败，不影响用户体验
                console.debug('[Dashboard] 实时更新失败:', error.message);
            }
        }, 333);
    }
    
    /**
     * 停止实时更新
     */
    stopRealtimeUpdates() {
        if (this.realtimeTimer) {
            clearInterval(this.realtimeTimer);
            this.realtimeTimer = null;
        }
    }
    
    /**
     * 更新实时数据到前端
     */
    updateRealtimeData(data) {
        if (data.simulation) {
            this.latestSimulation = data.simulation;
            this.updateConnectionStatus(
                data.simulation.running ? 'running' : 'connected',
                data.simulation.running ? 'SUMO仿真运行中' : '服务已连接',
                data.simulation.running
                    ? `时间步: ${data.simulation.current_step || 0}/${data.simulation.total_steps || '?'}`
                    : '地图与路口数据已加载'
            );
        }

        // 1. 更新统计信息
        if (data.statistics) {
            this.updateStatistics(data.statistics);
        }
        this.updateInferenceHud(data);
        
        // 2. 更新路口拥堵状态（用于热力图）
        if (data.junctions && this.map) {
            // 构建路口拥堵数据
            const congestionData = {};
            data.junctions.forEach(junction => {
                congestionData[junction.junction_id] = junction.congestion_level || 0;
            });
            
            // 更新地图上的拥堵热力图
            this.map.updateCongestion(congestionData);
        }
        
        // 3. 如果详情面板打开，更新详情（需要完整数据）
        if (this.panel && this.panel.isOpen()) {
            const currentJunctionId = this.panel.getCurrentJunctionId();
            if (currentJunctionId) {
                // 请求完整的路口详情数据
                this.fetchJunctionDetail(currentJunctionId);
            }
        }

        if (this.agentPanel && this.agentPanel.isOpen()) {
            const currentAgentId = this.agentPanel.getCurrentJunctionId();
            if (currentAgentId) {
                this.fetchAgentDetail(currentAgentId);
            }
        }
    }
    
    /**
     * 更新统计信息显示
     */
    updateStatistics(stats) {
        // 保存实时统计数据
        this.realtimeStats = stats;
        
        // 如果统计面板是打开的，更新显示
        const overlay = document.getElementById('stats-overlay');
        if (overlay && overlay.style.display !== 'none') {
            this.refreshStatisticsPanel();
        }
    }
    
    /**
     * 刷新统计面板显示
     */
    refreshStatisticsPanel() {
        const content = document.getElementById('stats-content');
        if (!content) return;
        
        const stats = this.realtimeStats || {
            total_vehicles: 0,
            avg_speed: 0,
            total_waiting: 0,
            active_junctions: 0
        };
        
        // 从网络数据计算基本统计
        const networkStats = this.calculateStatistics();
        
        // 检查是否需要初始化HTML结构
        if (!content.querySelector('.stats-grid')) {
            content.innerHTML = `
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-label">总路口数</div>
                        <div class="stat-value" id="stat-total-junctions">0</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">活跃路口</div>
                        <div class="stat-value" style="color: #00ff88;" id="stat-active-junctions">0</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">总车辆数</div>
                        <div class="stat-value" style="color: #00ff88;" id="stat-total-vehicles">0</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">平均速度</div>
                        <div class="stat-value" style="color: #00ff88;" id="stat-avg-speed">0 km/h</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">等待车辆</div>
                        <div class="stat-value" style="color: #ff6b6b;" id="stat-total-waiting">0</div>
                    </div>
                </div>
            `;
        }
        
        // 只更新数值，不重建HTML结构
        const updateElement = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.textContent = value;
        };
        
        updateElement('stat-total-junctions', networkStats.totalJunctions);
        updateElement('stat-active-junctions', stats.active_junctions);
        updateElement('stat-total-vehicles', stats.total_vehicles);
        updateElement('stat-avg-speed', `${(stats.avg_speed * 3.6).toFixed(2)} km/h`);
        updateElement('stat-total-waiting', stats.total_waiting);
    }
}

// 全局Dashboard实例
let dashboard = null;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    dashboard = new Dashboard();
});

// 点击外部关闭显示设置面板
document.addEventListener('click', (event) => {
    const panel = document.getElementById('display-controls');
    const settingsBtn = event.target.closest('.toolbar-btn');
    
    if (panel && panel.style.display === 'block') {
        // 如果点击的不是设置按钮且不在面板内，则关闭面板
        if (!settingsBtn && !panel.contains(event.target)) {
            panel.style.display = 'none';
        }
    }
});

// 点击统计浮窗背景关闭
document.addEventListener('click', (event) => {
    if (event.target.id === 'stats-overlay') {
        dashboard.hideStatistics();
    }
});

// ========== 左侧工具栏控制 ==========

/**
 * 切换侧边栏展开/折叠状态
 */
Dashboard.prototype.toggleSidebar = function() {
    const sidebar = document.getElementById('tool-sidebar');
    if (sidebar) {
        this.sidebarCollapsed = !this.sidebarCollapsed;
        if (this.sidebarCollapsed) {
            sidebar.classList.add('collapsed');
        } else {
            sidebar.classList.remove('collapsed');
        }
    }
};

/**
 * 打开工具模块
 * @param {string} toolName - 工具名称 (agents, data, models, comparison)
 */
Dashboard.prototype.openTool = function(toolName) {
    console.log(`打开工具: ${toolName}`);
    
    // 更新当前工具状态
    this.currentTool = toolName;
    
    // 更新UI激活状态
    const toolItems = document.querySelectorAll('.tool-item');
    toolItems.forEach(item => {
        item.classList.remove('active');
    });
    
    // 找到对应的工具项并激活
    const clickedItem = (typeof event !== 'undefined' && event.target)
        ? event.target.closest('.tool-item')
        : Array.from(toolItems).find(item => (item.getAttribute('onclick') || '').includes(`'${toolName}'`));
    if (clickedItem) {
        clickedItem.classList.add('active');
    }
    
    // TODO: 根据不同的工具名称，加载对应的模块
    switch(toolName) {
        case 'agents':
            this.openAgentsTool();
            break;
        case 'data':
            this.openDataTool();
            break;
        case 'models':
            this.openModelsTool();
            break;
        case 'comparison':
            this.openComparisonTool();
            break;
        default:
            console.warn(`未知的工具: ${toolName}`);
    }
};

/**
 * 打开智能体列表工具
 */
Dashboard.prototype.openAgentsTool = async function() {
    try {
        const htmlResponse = await fetch('/static/html/agents-tool.html');
        const html = await htmlResponse.text();

        let toolContainer = document.getElementById('tool-container');
        if (!toolContainer) {
            toolContainer = document.createElement('div');
            toolContainer.id = 'tool-container';
            document.body.appendChild(toolContainer);
        }

        toolContainer.innerHTML = html;
        toolContainer.style.display = 'block';

        const panel = document.getElementById('agents-tool-panel');
        panel.classList.add('active');
        panel.style.display = 'flex';

        this.agentPanel = new JunctionPanel('agents-detail-panel', {
            titleId: 'agents-detail-title',
            contentId: 'agents-detail-content',
            useOpenClass: false
        });

        this.bindAgentsToolEvents();
        await this.loadAgentsList();
    } catch (error) {
        console.error('打开智能体列表工具失败:', error);
        alert('打开智能体列表工具失败: ' + error.message);
    }
};

Dashboard.prototype.bindAgentsToolEvents = function() {
    const searchInput = document.getElementById('agents-search');
    const typeFilter = document.getElementById('agents-type-filter');

    if (searchInput) {
        searchInput.addEventListener('input', () => {
            this.renderAgentsList(this._cachedAgentsList || []);
        });
    }

    if (typeFilter) {
        typeFilter.addEventListener('change', () => {
            this.renderAgentsList(this._cachedAgentsList || []);
        });
    }
};

Dashboard.prototype.loadAgentsList = async function() {
    try {
        const [summaryResponse, configResponse] = await Promise.all([
            fetch(`${this.apiBaseUrl}/junctions/summary`),
            fetch(`${this.apiBaseUrl}/config`)
        ]);

        if (!summaryResponse.ok) {
            throw new Error(`智能体摘要加载失败: HTTP ${summaryResponse.status}`);
        }

        const summaryData = await summaryResponse.json();
        const configData = configResponse.ok ? await configResponse.json() : null;

        if (!summaryData.success) {
            throw new Error(summaryData.message || summaryData.error || '智能体摘要加载失败');
        }

        const agents = (summaryData.summaries || []).slice().sort((a, b) => {
            return String(a.junction_id).localeCompare(String(b.junction_id), 'zh-CN', { numeric: true });
        });

        this._cachedAgentsList = agents;

        const currentMap = configData?.config?.map?.default_map || '未知';
        const countEl = document.getElementById('agents-count');
        const mapEl = document.getElementById('agents-current-map');
        const metaEl = document.getElementById('agents-list-meta');

        if (countEl) countEl.textContent = String(agents.length);
        if (mapEl) mapEl.textContent = currentMap;
        if (metaEl) metaEl.textContent = `共 ${agents.length} 个智能体`;

        this.renderAgentsList(agents);
    } catch (error) {
        console.error('加载智能体列表失败:', error);
        const listContainer = document.getElementById('agents-list');
        if (listContainer) {
            listContainer.innerHTML = `
                <div class="loading-message" style="color: var(--error-color);">
                    加载失败: ${error.message}
                </div>
            `;
        }
    }
};

Dashboard.prototype.fetchJunctionState = async function(junctionId) {
    const response = await fetch(`${this.apiBaseUrl}/junctions/${junctionId}`);
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    if (data.error || !data.junction) {
        throw new Error(data.error || '路口详情加载失败');
    }

    return data.junction;
};

Dashboard.prototype.renderAgentsList = function(agents) {
    const listContainer = document.getElementById('agents-list');
    const metaEl = document.getElementById('agents-list-meta');
    if (!listContainer) return;

    const searchText = (document.getElementById('agents-search')?.value || '').trim().toLowerCase();
    const typeFilter = document.getElementById('agents-type-filter')?.value || '';

    const filteredAgents = agents.filter(agent => {
        const matchSearch = !searchText || String(agent.junction_id).toLowerCase().includes(searchText);
        const matchType = !typeFilter || agent.junction_type === typeFilter;
        return matchSearch && matchType;
    });

    if (metaEl) {
        metaEl.textContent = `显示 ${filteredAgents.length} / ${agents.length} 个智能体`;
    }

    if (filteredAgents.length === 0) {
        listContainer.innerHTML = '<div class="loading-message">没有符合条件的智能体</div>';
        return;
    }

    listContainer.innerHTML = filteredAgents.map(agent => {
        const typeText = agent.junction_type === 'traffic_light' ? '信号灯' : '优先通行';
        const activeText = agent.is_active ? '活跃' : '未激活';
        const congestion = ((agent.congestion_level || 0) * 100).toFixed(0);

        return `
            <div class="agent-list-item" onclick="dashboard.selectAgentItem('${agent.junction_id}')">
                <div class="agent-item-top">
                    <div class="agent-item-title">${agent.junction_id}</div>
                    <div class="agent-item-badge">${typeText}</div>
                </div>
                <div class="agent-item-meta">
                    <span>状态: ${activeText}</span>
                    <span>车辆: ${agent.total_vehicles || 0}</span>
                    <span>停车: ${agent.total_halting || 0}</span>
                    <span>拥堵: ${congestion}%</span>
                </div>
            </div>
        `;
    }).join('');
};

Dashboard.prototype.selectAgentItem = async function(junctionId) {
    document.querySelectorAll('.agent-list-item').forEach(item => {
        item.classList.remove('active');
    });

    const selected = Array.from(document.querySelectorAll('.agent-list-item')).find(item => {
        return item.querySelector('.agent-item-title')?.textContent === junctionId;
    });

    if (selected) {
        selected.classList.add('active');
    }

    try {
        const junction = await this.fetchJunctionState(junctionId);

        if (this.agentPanel) {
            this.agentPanel.open(junctionId, junction);
        }

        if (this.map) {
            this.map.selectedJunction = junctionId;
            this.map.render();
        }
    } catch (error) {
        console.error('加载智能体详情失败:', error);
        alert('加载智能体详情失败: ' + error.message);
    }
};

Dashboard.prototype.fetchAgentDetail = async function(junctionId) {
    try {
        const junction = await this.fetchJunctionState(junctionId);
        if (this.agentPanel && this.agentPanel.isOpen() && this.agentPanel.getCurrentJunctionId() === junctionId) {
            this.agentPanel.update(junction);
        }
    } catch (error) {
        console.debug('[Dashboard] 更新智能体详情失败:', error.message);
    }
};

/**
 * 打开实时交通数据工具
 */
Dashboard.prototype.openDataTool = async function() {
    try {
        // 获取TDengine配置
        const response = await fetch(`${this.apiBaseUrl}/tools/data/tdengine-config`);
        const result = await response.json();
        
        if (!result.success) {
            alert('无法获取TDengine配置: ' + result.message);
            return;
        }
        
        const config = result.config;
        
        // 加载工具面板HTML
        const htmlResponse = await fetch('/static/html/realtime-traffic-data-tool.html');
        const html = await htmlResponse.text();
        
        // 创建或获取工具容器
        let toolContainer = document.getElementById('tool-container');
        if (!toolContainer) {
            toolContainer = document.createElement('div');
            toolContainer.id = 'tool-container';
            document.body.appendChild(toolContainer);
        }
        
        // 插入HTML
        toolContainer.innerHTML = html;
        toolContainer.style.display = 'block';  // 确保容器可见
        const panel = document.getElementById('data-tool-panel');
        panel.classList.add('active');
        panel.style.display = 'block';  // 确保面板可见
        
        // 显示TDengine URL
        const urlElement = document.getElementById('tdengine-url');
        if (urlElement) {
            urlElement.textContent = config.url;
        }
        
        // 设置iframe src，使用TDengine Web界面
        const iframe = document.getElementById('tdengine-iframe');
        iframe.src = config.url;
        
        // iframe加载完成后隐藏加载提示
        iframe.onload = function() {
            iframe.classList.add('loaded');
            const loadingInfo = document.getElementById('tdengine-loading');
            if (loadingInfo) {
                loadingInfo.style.opacity = '0';
                setTimeout(() => {
                    loadingInfo.style.display = 'none';
                }, 300);
            }
        };
        
        // 超时处理
        setTimeout(() => {
            if (!iframe.classList.contains('loaded')) {
                const loadingInfo = document.getElementById('tdengine-loading');
                if (loadingInfo) {
                    loadingInfo.innerHTML = `
                        <div class="loading-spinner">⚠️</div>
                        <p style="color: var(--warning-color);">连接超时</p>
                        <p class="info-text">请检查 TDengine 服务是否运行</p>
                        <p class="info-text">地址: ${config.url}</p>
                    `;
                }
            }
        }, 10000);
        
    } catch (error) {
        console.error('打开实时交通数据工具失败:', error);
        alert('打开实时交通数据工具失败: ' + error.message);
    }
};

/**
 * 打开模型管理工具
 */
Dashboard.prototype.openModelsTool = async function() {
    try {
        // 加载工具面板HTML
        const htmlResponse = await fetch('/static/html/models-tool.html');
        const html = await htmlResponse.text();
        
        // 创建或获取工具容器
        let toolContainer = document.getElementById('tool-container');
        if (!toolContainer) {
            toolContainer = document.createElement('div');
            toolContainer.id = 'tool-container';
            document.body.appendChild(toolContainer);
        }
        
        // 插入HTML
        toolContainer.innerHTML = html;
        toolContainer.style.display = 'block';  // 确保容器可见
        const panel = document.getElementById('models-tool-panel');
        panel.classList.add('active');
        panel.style.display = 'block';  // 确保面板可见
        
        // 绑定事件
        this.bindModelsToolEvents();
        
        // 加载模型列表
        this.loadModelsList();
        
    } catch (error) {
        console.error('打开模型管理工具失败:', error);
        alert('打开模型管理工具失败: ' + error.message);
    }
};

/**
 * 绑定模型工具事件
 */
Dashboard.prototype.bindModelsToolEvents = function() {
    // 搜索框
    const searchInput = document.getElementById('model-search');
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            this.filterModelsList();
        });
    }
    
    // 算法过滤
    const algorithmFilter = document.getElementById('algorithm-filter');
    if (algorithmFilter) {
        algorithmFilter.addEventListener('change', () => {
            this.loadModelsList();
        });
    }
};

/**
 * 加载模型列表
 */
Dashboard.prototype.loadModelsList = async function() {
    try {
        const algorithmFilter = document.getElementById('algorithm-filter');
        const algorithm = algorithmFilter ? algorithmFilter.value : '';
        
        const params = new URLSearchParams();
        if (algorithm) {
            params.append('algorithm', algorithm);
        }
        
        const response = await fetch(`${this.apiBaseUrl}/tools/models/list?${params}`);
        const result = await response.json();
        
        if (!result.success) {
            throw new Error(result.message);
        }
        
        this.renderModelsList(result.models);
        
    } catch (error) {
        console.error('加载模型列表失败:', error);
        const listContainer = document.getElementById('models-list');
        if (listContainer) {
            listContainer.innerHTML = `
                <div class="loading-message" style="color: var(--danger-color);">
                    加载失败: ${error.message}
                </div>
            `;
        }
    }
};

/**
 * 渲染模型列表
 */
Dashboard.prototype.renderModelsList = function(models) {
    const listContainer = document.getElementById('models-list');
    if (!listContainer) return;
    
    if (models.length === 0) {
        listContainer.innerHTML = '<div class="loading-message">没有找到模型</div>';
        return;
    }
    
    listContainer.innerHTML = models.map(model => `
        <div class="model-item" data-model-id="${model.id}" onclick="dashboard.showModelDetail('${model.id}')">
            <div class="model-item-header">
                <span class="model-item-name">${model.network}/${model.name}</span>
                <span class="model-item-algorithm">${model.algorithm.toUpperCase()}</span>
            </div>
            <div class="model-item-info">
                ${model.weight_count ? `<span>💾 ${model.weight_count} 个权重文件</span>` : ''}
                ${model.max_epoch ? `<span>🔄 Epoch: ${model.max_epoch}</span>` : ''}
            </div>
        </div>
    `).join('');
};

/**
 * 显示模型详情
 */
Dashboard.prototype.showModelDetail = async function(modelId) {
    try {
        // 更新选中状态
        document.querySelectorAll('.model-item').forEach(item => {
            item.classList.remove('active');
        });
        const selectedItem = document.querySelector(`[data-model-id="${modelId}"]`);
        if (selectedItem) {
            selectedItem.classList.add('active');
        }
        
        // 显示详情区域
        const placeholder = document.getElementById('detail-placeholder');
        const content = document.getElementById('detail-content');
        if (placeholder) placeholder.style.display = 'none';
        if (content) content.style.display = 'block';
        
        // 获取模型详情（对modelId进行URL编码）
        const encodedModelId = encodeURIComponent(modelId);
        const response = await fetch(`${this.apiBaseUrl}/tools/models/info/${encodedModelId}`);
        const result = await response.json();
        
        if (!result.success) {
            throw new Error(result.message);
        }
        
        this.renderModelDetail(result.model_info);
        
    } catch (error) {
        console.error('加载模型详情失败:', error);
        alert('加载模型详情失败: ' + error.message);
    }
};

/**
 * 渲染模型详情
 */
Dashboard.prototype.renderModelDetail = function(modelInfo) {
    // 标题和徽章
    const titleEl = document.getElementById('detail-title');
    const algorithmEl = document.getElementById('detail-algorithm');
    const statusEl = document.getElementById('detail-status');
    
    if (titleEl) titleEl.textContent = modelInfo.name;
    if (algorithmEl) algorithmEl.textContent = modelInfo.algorithm.toUpperCase();
    if (statusEl) statusEl.textContent = modelInfo.has_weights ? '已训练' : '未完成';
    
    // 训练指标图
    const metricsImg = document.getElementById('metrics-image');
    const metricsError = document.getElementById('metrics-error');
    
    if (modelInfo.has_metrics) {
        if (metricsImg) {
            metricsImg.src = `${this.apiBaseUrl}/tools/models/file/${modelInfo.id}/metrics`;
            metricsImg.style.display = 'block';
        }
        if (metricsError) metricsError.style.display = 'none';
    } else {
        if (metricsImg) metricsImg.style.display = 'none';
        if (metricsError) metricsError.style.display = 'block';
    }
    
    // 训练参数
    const paramsGrid = document.getElementById('params-grid');
    if (paramsGrid && modelInfo.parameters) {
        // LibSignal的配置参数名称
        const importantParams = [
            'sim', 'algorithm', 'demand', 'simlen', 'sim_steps',
            'n_epochs', 'batch', 'learning_rate', 'gamma', 'action_interval',
            'save_epochs', 'description', 'model_name'
        ];
        
        const paramLabels = {
            'sim': '路网场景',
            'algorithm': '算法',
            'demand': '交通需求',
            'simlen': '推理仿真步数',
            'sim_steps': '训练仿真步数',
            'n_epochs': '训练轮数',
            'batch': 'Batch Size',
            'learning_rate': '学习率',
            'gamma': 'Gamma',
            'action_interval': '动作间隔',
            'save_epochs': '保存间隔',
            'description': '描述',
            'model_name': '模型名称'
        };
        
        const paramItems = importantParams
            .filter(key => modelInfo.parameters[key] !== undefined)
            .map(key => `
                <div class="param-item">
                    <div class="param-label">${paramLabels[key] || key}</div>
                    <div class="param-value">${JSON.stringify(modelInfo.parameters[key])}</div>
                </div>
            `).join('');
        
        paramsGrid.innerHTML = paramItems || '<div class="loading-message">无参数信息</div>';
    }
    
    // 文件信息
    const filesInfo = document.getElementById('files-info');
    if (filesInfo) {
        filesInfo.innerHTML = `
            ${modelInfo.has_weights ? `
                <div class="file-info-item">
                    <div class="file-icon">💾</div>
                    <div class="file-info-text">
                        <div class="file-info-name">模型权重</div>
                        <div class="file-info-meta">${modelInfo.weight_count} 个 .pt 文件</div>
                    </div>
                </div>
            ` : ''}
            ${modelInfo.has_params ? `
                <div class="file-info-item">
                    <div class="file-icon">⚙️</div>
                    <div class="file-info-text">
                        <div class="file-info-name">训练参数</div>
                        <div class="file-info-meta">training_params.json</div>
                    </div>
                </div>
            ` : ''}
            ${modelInfo.has_metrics ? `
                <div class="file-info-item">
                    <div class="file-icon">📊</div>
                    <div class="file-info-text">
                        <div class="file-info-name">训练指标</div>
                        <div class="file-info-meta">training_metrics.png</div>
                    </div>
                </div>
            ` : ''}
        `;
    }
};

/**
 * 打开持续学习工具
 */
Dashboard.prototype.openComparisonTool = async function() {
    try {
        const response = await fetch('/static/html/continual-learning-tool.html');
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const html = await response.text();
        
        let container = document.getElementById('tool-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'tool-container';
            document.body.appendChild(container);
        }
        
        container.innerHTML = html;
        container.style.display = 'block';
        
        // 激活tool-panel
        const toolPanel = container.querySelector('.tool-panel');
        if (toolPanel) {
            toolPanel.classList.add('active');
            toolPanel.style.display = 'flex';
        }
        
        // 等待DOM更新后再初始化
        setTimeout(() => {
            this.initComparisonTool();
            // 检查并恢复对比任务状态
            this.checkAndRestoreComparisonStatus();
        }, 100);
        
    } catch (error) {
        console.error('加载持续学习工具失败:', error);
        alert('加载持续学习工具失败: ' + error.message);
    }
};

Dashboard.prototype.initComparisonTool = function() {
    try {
        // 初始化变量
        this.comparisonStatusInterval = null;
        this.currentExperimentId = null;
        
        // 加载默认配置
        this.loadDefaultComparisonConfig();
        this.loadAvailableMapsForComparison();
        
        // 添加第一个模型选择框
        this.addComparisonModel();
        
    } catch (error) {
        console.error('初始化对比实验工具失败:', error);
    }
};

Dashboard.prototype.addComparisonModel = function() {
    const container = document.getElementById('comparison-models-list');
    if (!container) {
        console.warn('对比模型列表容器未找到');
        return;
    }
    
    const modelCount = container.children.length;
    const colors = ['#4CAF50', '#2196F3', '#FF9800', '#E91E63', '#9C27B0', '#00BCD4', '#FFC107', '#00BCD4'];
    const color = colors[modelCount % colors.length];
    
    const modelItem = document.createElement('div');
    modelItem.className = 'model-selection-item';
    modelItem.innerHTML = `
        <div class="color-indicator" style="background-color: ${color}"></div>
        <select class="model-select" data-color="${color}">
            <option value="">选择模型...</option>
        </select>
        <button class="remove-item-btn" onclick="dashboard.removeComparisonModel(this)">移除</button>
    `;
    
    container.appendChild(modelItem);
    
    // 加载可用模型列表
    const selectElement = modelItem.querySelector('.model-select');
    if (selectElement) {
        this.loadModelsForComparison(selectElement);
    }
};

Dashboard.prototype.removeComparisonModel = function(btn) {
    const item = btn.closest('.model-selection-item');
    if (item) {
        item.remove();
    }
};

Dashboard.prototype.loadModelsForComparison = function(selectElement) {
    fetch('/api/tools/models/list')
        .then(response => response.json())
        .then(data => {
            if (data.success && data.models) {
                // 首先清空选项（保留第一个"选择模型..."）
                selectElement.innerHTML = '<option value="">选择模型...</option>';
                
                data.models.forEach(model => {
                    const option = document.createElement('option');
                    option.value = model.id;
                    // 使用 latest_epoch 或 max_epoch
                    const epoch = model.latest_epoch || model.max_epoch || 'N/A';
                    
                    // 显示格式: 网络/模型 (算法) - Epoch X
                    // 例如: "manhattan/test (colight) - Epoch 160"
                    const displayName = `${model.network}/${model.name} (${model.algorithm}) - Epoch ${epoch}`;
                    option.textContent = displayName;
                    
                    // 存储 epoch 信息用于后续提交
                    option.dataset.epoch = epoch;
                    selectElement.appendChild(option);
                });
            }
        })
        .catch(error => {
            console.error('加载模型列表失败:', error);
        });
};

/**
 * 加载可用地图列表（对比实验工具）
 */
Dashboard.prototype.loadAvailableMapsForComparison = async function() {
    try {
        const response = await fetch('/api/maps/list');
        const data = await response.json();
        
        if (data.success && data.maps) {
            const select = document.getElementById('test-scenario');
            if (select) {
                select.innerHTML = '';
                data.maps.forEach(map => {
                    const option = document.createElement('option');
                    option.value = map.id;
                    option.textContent = `${map.name} - ${map.description}`;
                    if (map.id === data.current_map) {
                        option.selected = true;
                    }
                    select.appendChild(option);
                });
            }
        }
    } catch (error) {
        console.error('加载地图列表失败:', error);
        // 如果加载失败，使用默认值
        const select = document.getElementById('test-scenario');
        if (select) {
            select.innerHTML = '<option value="81">81路口 (默认)</option>';
        }
    }
};

Dashboard.prototype.loadDefaultComparisonConfig = function() {
    const setValueIfExists = (id, value) => {
        const element = document.getElementById(id);
        if (element) {
            element.value = value;
        } else {
            console.warn(`元素未找到: ${id}`);
        }
    };
    
    setValueIfExists('experiment-name', '');
    setValueIfExists('experiment-description', '');
    // test-scenario 将由 loadAvailableMapsForComparison() 动态加载  // 默认使用81路口
    setValueIfExists('test-demand', 'onfly');  // LibSignal默认使用onfly
    setValueIfExists('test-sim-length', '3600');
    setValueIfExists('test-traffic-scale', '2.0');  // 与LibSignal默认值一致
};

Dashboard.prototype.startComparison = function() {
    const experimentName = document.getElementById('experiment-name').value.trim();
    if (!experimentName) {
        alert('请输入实验名称');
        return;
    }
    
    // 收集选中的模型
    const models = [];
    document.querySelectorAll('.model-select').forEach(select => {
        if (select.value) {
            const selectedOption = select.options[select.selectedIndex];
            models.push({
                id: select.value,
                name: selectedOption.text,
                epoch: selectedOption.dataset.epoch || 'latest',  // 添加 epoch 信息
                color: select.dataset.color
            });
        }
    });
    
    // 收集基准算法
    const baselines = [];
    document.querySelectorAll('.baseline-checkbox:checked').forEach(checkbox => {
        baselines.push(checkbox.value);
    });
    
    // 验证至少有1个对比对象
    if (models.length + baselines.length < 1) {
        alert('请至少选择1个模型或算法进行对比');
        return;
    }
    
    // 收集评估指标
    const metrics = [];
    document.querySelectorAll('.metric-checkbox:checked').forEach(checkbox => {
        metrics.push(checkbox.value);
    });
    
    if (metrics.length === 0) {
        alert('请至少选择一个评估指标');
        return;
    }
    
    // 构建配置
    const config = {
        name: experimentName,  // 使用 'name' 而非 'experiment_name'
        description: document.getElementById('experiment-description').value.trim(),
        scenario: document.getElementById('test-scenario').value,
        demand: document.getElementById('test-demand').value,
        sim_length: parseInt(document.getElementById('test-sim-length').value),
        traffic_scale: parseFloat(document.getElementById('test-traffic-scale').value),
        models: models,
        baselines: baselines,
        metrics: metrics
    };
    
    // 显示状态面板
    document.getElementById('comparison-status-placeholder').style.display = 'none';
    document.getElementById('comparison-status-content').style.display = 'block';
    document.getElementById('comparison-status-badge').textContent = '准备中';
    document.getElementById('comparison-status-badge').className = 'status-badge preparing';
    
    this.addComparisonLog('info', '正在启动对比实验...');
    
    // 调用后端API启动对比实验
    fetch('/api/tools/comparison/start', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(config)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            this.currentExperimentId = data.experiment_id;
            this.addComparisonLog('success', data.message);
            document.getElementById('comparison-status-badge').textContent = '运行中';
            document.getElementById('comparison-status-badge').className = 'status-badge running';
            
            // 初始化模型进度显示
            this.initModelsProgress(config.models, config.baselines);
            
            // 开始轮询状态
            this.startComparisonStatusPolling();
        } else {
            this.addComparisonLog('error', '启动失败: ' + data.message);
            document.getElementById('comparison-status-badge').textContent = '启动失败';
            document.getElementById('comparison-status-badge').className = 'status-badge error';
        }
    })
    .catch(error => {
        this.addComparisonLog('error', '请求失败: ' + error.message);
        document.getElementById('comparison-status-badge').textContent = '错误';
        document.getElementById('comparison-status-badge').className = 'status-badge error';
    });
};

Dashboard.prototype.stopComparison = function() {
    if (!this.currentExperimentId) {
        alert('没有正在运行的实验');
        return;
    }
    
    if (confirm('确定要停止实验吗？')) {
        this.addComparisonLog('warning', '正在停止实验...');
        
        fetch('/api/tools/comparison/stop', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({experiment_id: this.currentExperimentId})
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                this.addComparisonLog('info', data.message);
                document.getElementById('comparison-status-badge').textContent = '已停止';
                document.getElementById('comparison-status-badge').className = 'status-badge stopped';
                this.stopComparisonStatusPolling();
            } else {
                this.addComparisonLog('error', '停止失败: ' + data.message);
            }
        })
        .catch(error => {
            this.addComparisonLog('error', '请求失败: ' + error.message);
        });
    }
};

Dashboard.prototype.initModelsProgress = function(models, baselines) {
    const container = document.getElementById('models-progress-list');
    if (!container) return;
    
    container.innerHTML = '';
    
    // 添加模型进度
    models.forEach(model => {
        const item = document.createElement('div');
        item.className = 'model-progress-item';
        item.dataset.modelId = model.id;
        item.innerHTML = `
            <div class="model-name" style="border-left: 3px solid ${model.color}; padding-left: 8px;">
                ${model.name}
            </div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: 0%; background-color: ${model.color};"></div>
            </div>
            <div class="status-text">等待中</div>
        `;
        container.appendChild(item);
    });
    
    // 添加基准算法进度
    const baselineColors = {
        'fixedtime': '#607D8B',
        'maxpressure': '#795548',
        'greenwave': '#009688'
    };
    
    baselines.forEach(baseline => {
        const item = document.createElement('div');
        item.className = 'model-progress-item';
        item.dataset.modelId = baseline;
        item.innerHTML = `
            <div class="model-name" style="border-left: 3px solid ${baselineColors[baseline] || '#999'}; padding-left: 8px;">
                ${baseline}
            </div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: 0%; background-color: ${baselineColors[baseline] || '#999'};"></div>
            </div>
            <div class="status-text">等待中</div>
        `;
        container.appendChild(item);
    });
};

/**
 * 检查并恢复对比任务状态
 * 重新打开对比工具时，检查后台是否有正在进行的对比任务
 */
Dashboard.prototype.checkAndRestoreComparisonStatus = async function() {
    try {
        const response = await fetch(`${this.apiBaseUrl}/tools/comparison/status`);
        const result = await response.json();
        
        if (result.success && result.experiment_id) {
            console.log('检测到正在进行的对比任务，恢复状态显示');
            
            // 保存实验ID
            this.currentExperimentId = result.experiment_id;
            
            // 显示结果面板
            const configPanel = document.getElementById('comparison-config-panel');
            const resultsPanel = document.getElementById('comparison-results-panel');
            if (configPanel && resultsPanel) {
                configPanel.style.display = 'none';
                resultsPanel.style.display = 'block';
            }
            
            // 更新状态显示
            this.updateComparisonStatusDisplay(result);
            
            // 启动状态轮询
            this.startComparisonStatusPolling();
        }
    } catch (error) {
        console.error('检查对比任务状态失败:', error);
        // 静默失败，不影响正常使用
    }
};

Dashboard.prototype.startComparisonStatusPolling = function() {
    this.stopComparisonStatusPolling();
    
    this.updateComparisonStatus();
    this.fetchComparisonLogs();  // 添加日志轮询
    
    this.comparisonStatusInterval = setInterval(() => {
        this.updateComparisonStatus();
        this.fetchComparisonLogs();  // 添加日志轮询
    }, 3000);
};

Dashboard.prototype.stopComparisonStatusPolling = function() {
    if (this.comparisonStatusInterval) {
        clearInterval(this.comparisonStatusInterval);
        this.comparisonStatusInterval = null;
    }
};

Dashboard.prototype.updateComparisonStatus = function() {
    if (!this.currentExperimentId) return;
    
    fetch(`/api/tools/comparison/status/${this.currentExperimentId}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 更新总体进度
                const overallProgress = data.overall_progress || 0;
                document.getElementById('overall-progress-fill').style.width = overallProgress + '%';
                document.getElementById('overall-progress-text').textContent = overallProgress.toFixed(1) + '%';
                
                // 更新各模型进度
                if (data.models_status) {
                    Object.entries(data.models_status).forEach(([modelId, status]) => {
                        const item = document.querySelector(`[data-model-id="${modelId}"]`);
                        if (item) {
                            const progressBar = item.querySelector('.progress-fill');
                            const statusText = item.querySelector('.status-text');
                            
                            if (progressBar) {
                                progressBar.style.width = (status.progress || 0) + '%';
                            }
                            if (statusText) {
                                statusText.textContent = status.status || '运行中';
                            }
                        }
                    });
                }
                
                // 检查是否完成
                if (data.is_completed) {
                    this.stopComparisonStatusPolling();
                    document.getElementById('comparison-status-badge').textContent = '已完成';
                    document.getElementById('comparison-status-badge').className = 'status-badge success';
                    this.addComparisonLog('success', '实验完成！');
                    
                    // 加载结果
                    this.loadComparisonResults();
                }
            }
        })
        .catch(error => {
            console.error('获取实验状态失败:', error);
        });
};

Dashboard.prototype.loadComparisonResults = function() {
    if (!this.currentExperimentId) return;
    
    fetch(`/api/tools/comparison/results/${this.currentExperimentId}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 显示结果可视化区域
                document.getElementById('comparison-results-viz').style.display = 'block';
                
                // 渲染对比图表
                this.renderComparisonCharts(data.results, data.chart_file);
            }
        })
        .catch(error => {
            console.error('加载实验结果失败:', error);
        });
};

Dashboard.prototype.renderComparisonCharts = function(results, chartFile) {
    const container = document.getElementById('comparison-charts-container');
    if (!container) return;
    
    // 清空容器
    container.innerHTML = '';
    
    // 显示图表
    if (chartFile) {
        const chartDiv = document.createElement('div');
        chartDiv.style.textAlign = 'center';
        chartDiv.style.padding = '20px';
        chartDiv.style.backgroundColor = '#fff';
        chartDiv.style.borderRadius = '8px';
        chartDiv.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)';
        chartDiv.style.marginBottom = '20px';
        
        const chartImg = document.createElement('img');
        chartImg.src = `/api/tools/comparison/chart/${chartFile}`;
        chartImg.alt = '对比图表';
        chartImg.style.maxWidth = '100%';
        chartImg.style.height = 'auto';
        chartImg.style.borderRadius = '4px';
        
        // 添加加载错误处理
        chartImg.onerror = function() {
            chartDiv.innerHTML = '<p style="color: #999;">图表加载失败</p>';
        };
        
        chartDiv.appendChild(chartImg);
        container.appendChild(chartDiv);
    }
    
};

Dashboard.prototype.exportComparisonResults = function() {
    if (!this.currentExperimentId) return;
    
    window.open(`/api/tools/comparison/export/${this.currentExperimentId}`, '_blank');
};

Dashboard.prototype.downloadComparisonReport = function() {
    if (!this.currentExperimentId) return;
    
    fetch('/api/tools/comparison/report', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({experiment_id: this.currentExperimentId})
    })
    .then(response => response.blob())
    .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `comparison_report_${this.currentExperimentId}.pdf`;
        a.click();
        window.URL.revokeObjectURL(url);
    })
    .catch(error => {
        console.error('下载报告失败:', error);
        alert('下载报告失败');
    });
};

Dashboard.prototype.fetchComparisonLogs = function() {
    fetch('/api/tools/comparison/logs?limit=100')
        .then(response => response.json())
        .then(data => {
            if (data.success && data.logs) {
                const logContainer = document.getElementById('comparison-log');
                if (!logContainer) return;
                
                // 清空现有日志（避免重复）
                const existingTimestamps = new Set(
                    Array.from(logContainer.children).map(child => child.dataset.timestamp)
                );
                
                // 只添加新日志
                data.logs.forEach(log => {
                    if (!existingTimestamps.has(log.timestamp)) {
                        const entry = document.createElement('div');
                        entry.className = `log-entry ${log.level}`;
                        entry.dataset.timestamp = log.timestamp;
                        const time = new Date(log.timestamp).toLocaleTimeString();
                        entry.textContent = `[${time}] ${log.message}`;
                        logContainer.appendChild(entry);
                    }
                });
                
                // 自动滚动到底部
                logContainer.scrollTop = logContainer.scrollHeight;
            }
        })
        .catch(error => {
            console.error('获取对比实验日志失败:', error);
    });
};

Dashboard.prototype.addComparisonLog = function(level, message) {
    const logContainer = document.getElementById('comparison-log');
    if (!logContainer) return;
    
    const now = new Date();
    const timestamp = now.toLocaleTimeString();
    const entry = document.createElement('div');
    entry.className = `log-entry ${level}`;
    entry.dataset.timestamp = now.toISOString();  // 添加timestamp用于去重
    entry.textContent = `[${timestamp}] ${message}`;
    
    logContainer.appendChild(entry);
    logContainer.scrollTop = logContainer.scrollHeight;
};

/**
 * 关闭当前工具
 */
Dashboard.prototype.closeTool = function() {
    const toolContainer = document.getElementById('tool-container');
    if (toolContainer) {
        // 移除所有active类
        const panels = toolContainer.querySelectorAll('.tool-panel');
        panels.forEach(panel => {
            panel.classList.remove('active');
            panel.style.display = 'none';
        });
        
        // 清空iframe src以停止加载
        const iframes = toolContainer.querySelectorAll('iframe');
        iframes.forEach(iframe => {
            iframe.src = 'about:blank';
        });
        
        // 隐藏容器
        toolContainer.style.display = 'none';
        toolContainer.innerHTML = '';
    }
    
    // 停止工具级轮询（不影响后台推理）
    if (this.comparisonStatusInterval) {
        clearInterval(this.comparisonStatusInterval);
        this.comparisonStatusInterval = null;
    }
    
    // 取消工具项激活状态
    const toolItems = document.querySelectorAll('.tool-item');
    toolItems.forEach(item => item.classList.remove('active'));
    
    // 保留当前工具信息，以便重新打开时恢复状态
    // this.currentTool = null;  // 不清空，用于恢复状态
};
