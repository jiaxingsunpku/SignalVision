/**
 * SUMO交通监控Dashboard - 路口详情面板
 * 
 * 负责渲染和更新路口的详细信息
 */

class JunctionPanel {
    constructor(panelId, options = {}) {
        this.panel = document.getElementById(panelId);
        this.panelContent = document.getElementById(options.contentId || 'panel-content');
        this.panelTitle = document.getElementById(options.titleId || 'panel-title');
        this.useOpenClass = options.useOpenClass !== false;
        this.currentJunctionId = null;
        this.historyWindowSize = options.historyWindowSize || 60;
    }
    
    /**
     * 打开面板并显示路口信息
     */
    open(junctionId, junctionData) {
        this.currentJunctionId = junctionId;
        if (this.useOpenClass && this.panel) {
            this.panel.classList.add('open');
        }
        this.render(junctionData);
    }
    
    /**
     * 关闭面板
     */
    close() {
        if (this.useOpenClass && this.panel) {
            this.panel.classList.remove('open');
        }
        this.currentJunctionId = null;
    }
    
    /**
     * 检查面板是否打开
     */
    isOpen() {
        if (this.useOpenClass && this.panel) {
            return this.panel.classList.contains('open');
        }
        return !!this.currentJunctionId;
    }
    
    /**
     * 获取当前显示的路口ID
     */
    getCurrentJunctionId() {
        return this.currentJunctionId;
    }
    
    /**
     * 更新面板内容（用于实时刷新）
     * 使用增量更新而不是全量替换，避免滚动位置重置
     */
    update(junctionData) {
        if (this.currentJunctionId && this.isOpen()) {
            this.updateDataOnly(junctionData);
        }
    }
    
    /**
     * 仅更新数据，不重新渲染整个面板（保持滚动位置）
     */
    updateDataOnly(data) {
        if (!data) return;
        
        // 更新实时交通指标
        if (data.metrics) {
            this.updateMetrics(data.metrics);
        }
        this.renderMetricsHistory(data.metrics_history, data.metrics);
        
        // 更新车道数据（这是最常变化的部分）
        if (data.incoming_lanes) {
            Object.entries(data.incoming_lanes).forEach(([laneId, lane]) => {
                const laneElement = this.panelContent.querySelector(`[data-lane-id="${laneId}"]`);
                if (laneElement) {
                    const statsHtml = `
                        <span title="车辆数">🚗 ${lane.vehicle_count}</span>
                        <span title="平均速度(km/h)">⏱️ ${(lane.mean_speed * 3.6).toFixed(1)}</span>
                        <span title="占有率">📊 ${lane.occupancy.toFixed(1)}%</span>
                        ${lane.halting_count > 0 ? `<span title="停车数" style="color: #ff9800;">⏸️ ${lane.halting_count}</span>` : ''}
                    `;
                    const statsElement = laneElement.querySelector('.lane-stats');
                    if (statsElement) statsElement.innerHTML = statsHtml;
                }
            });
        }
        
        if (data.outgoing_lanes) {
            Object.entries(data.outgoing_lanes).forEach(([laneId, lane]) => {
                const laneElement = this.panelContent.querySelector(`[data-lane-id="${laneId}"]`);
                if (laneElement) {
                    const statsHtml = `
                        <span title="车辆数">🚗 ${lane.vehicle_count}</span>
                        <span title="平均速度(km/h)">⏱️ ${(lane.mean_speed * 3.6).toFixed(1)}</span>
                        <span title="占有率">📊 ${lane.occupancy.toFixed(1)}%</span>
                        ${lane.halting_count > 0 ? `<span title="停车数" style="color: #ff9800;">⏸️ ${lane.halting_count}</span>` : ''}
                    `;
                    const statsElement = laneElement.querySelector('.lane-stats');
                    if (statsElement) statsElement.innerHTML = statsHtml;
                }
            });
        }
        
        // 更新信号灯状态（如果存在）
        if (data.traffic_light) {
            this.updateTrafficLight(data.traffic_light);
        }
        
        // 更新最后更新时间
        if (data.last_update_time) {
            this.updateInfoValue('最后更新', this.formatTimestamp(data.last_update_time));
        }
    }
    
    /**
     * 更新实时交通指标
     */
    updateMetrics(metrics) {
        // 更新当前车辆数
        this.updateInfoValue('当前车辆数', metrics.total_vehicles);
        
        // 更新平均速度
        this.updateInfoValue('平均速度', `${(metrics.average_speed * 3.6).toFixed(1)} km/h`);
        
        // 更新平均占有率
        this.updateInfoValue('平均占有率', `${metrics.average_occupancy.toFixed(1)}%`);
        
        // 更新停车车辆数
        const haltingElement = this.findInfoElement('停车车辆数');
        if (haltingElement) {
            haltingElement.textContent = metrics.total_halting;
            if (metrics.total_halting > 0) {
                haltingElement.classList.add('warning');
            } else {
                haltingElement.classList.remove('warning');
            }
        }
        
        // 更新拥堵级别
        const congestionElement = this.findInfoElement('拥堵级别');
        if (congestionElement) {
            congestionElement.className = `info-value ${this.getCongestionClass(metrics.congestion_level)}`;
            congestionElement.textContent = `${this.getCongestionText(metrics.congestion_level)} (${(metrics.congestion_level * 100).toFixed(0)}%)`;
        }
        
        // 更新最大队列长度
        this.updateInfoValue('最大队列长度', metrics.max_queue_length);
        
        // 更新累计统计
        if (metrics.total_vehicles_passed !== undefined) {
            this.updateInfoValue('通过车辆总数', metrics.total_vehicles_passed);
        }
        if (metrics.total_waiting_time !== undefined) {
            this.updateInfoValue('总等待时间', `${metrics.total_waiting_time.toFixed(1)} s`);
        }
    }
    
    /**
     * 更新信号灯状态
     */
    updateTrafficLight(trafficLight) {
        // 更新相位持续时间（当前相位已持续的时间）
        this.updateInfoValue('相位持续时间', `${trafficLight.phase_duration.toFixed(1)} s`);
        
        // 更新下次切换时间（距离下次可能切换的时间）
        this.updateInfoValue('下次切换时间', `${trafficLight.next_switch_time.toFixed(1)} s`);
        
        // 更新相位状态显示
        const phaseDisplay = this.panelContent.querySelector('.phase-display');
        if (phaseDisplay && trafficLight.phase_state) {
            phaseDisplay.innerHTML = this.renderPhaseState(trafficLight.phase_state);
        }
    }
    
    /**
     * 辅助方法：根据标签查找并更新值
     */
    updateInfoValue(label, value) {
        const element = this.findInfoElement(label);
        if (element) {
            element.textContent = value;
        }
    }
    
    /**
     * 辅助方法：根据标签查找信息元素
     */
    findInfoElement(label) {
        const labels = this.panelContent.querySelectorAll('.info-label');
        for (const labelElement of labels) {
            if (labelElement.textContent.trim() === label) {
                return labelElement.parentElement.querySelector('.info-value');
            }
        }
        return null;
    }
    
    /**
     * 渲染面板内容（完整渲染，用于首次打开）
     */
    render(data) {
        if (!data) {
            this.renderPlaceholder();
            return;
        }
        
        this.panelTitle.textContent = `路口 ${data.junction_id}`;
        
        const html = `
            <div class="junction-info">
                <!-- 基本信息 -->
                <div class="info-section">
                    <div class="section-title">基本信息</div>
                    <div class="info-grid">
                        <div class="info-item">
                            <div class="info-label">路口ID</div>
                            <div class="info-value">${data.junction_id}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">类型</div>
                            <div class="info-value">
                                ${data.junction_type === 'traffic_light' ? '🚦 信号灯' : '⚠️ 优先通行'}
                            </div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">位置 (X)</div>
                            <div class="info-value">${data.position[0].toFixed(1)}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">位置 (Y)</div>
                            <div class="info-value">${data.position[1].toFixed(1)}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">控制模式</div>
                            <div class="info-value">${this.getControlModeText(data.control_mode)}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">状态</div>
                            <div class="info-value ${data.is_active ? 'success' : 'error'}">
                                ${data.is_active ? '活跃' : '未激活'}
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- 实时交通指标 -->
                <div class="info-section">
                    <div class="section-title">实时交通指标</div>
                    <div class="info-grid">
                        <div class="info-item">
                            <div class="info-label">当前车辆数</div>
                            <div class="info-value">${data.metrics.total_vehicles}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">平均速度</div>
                            <div class="info-value">${(data.metrics.average_speed * 3.6).toFixed(1)} km/h</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">平均占有率</div>
                            <div class="info-value">${data.metrics.average_occupancy.toFixed(1)}%</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">停车车辆数</div>
                            <div class="info-value ${data.metrics.total_halting > 0 ? 'warning' : ''}">${data.metrics.total_halting}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">拥堵级别</div>
                            <div class="info-value ${this.getCongestionClass(data.metrics.congestion_level)}">
                                ${this.getCongestionText(data.metrics.congestion_level)} 
                                (${(data.metrics.congestion_level * 100).toFixed(0)}%)
                            </div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">最大队列长度</div>
                            <div class="info-value">${data.metrics.max_queue_length}</div>
                        </div>
                    </div>
                </div>

                <div class="info-section metrics-history-section">
                    <div class="section-title history-title">
                        <span>历史监测窗口</span>
                        <span class="history-window-label">最近 ${this.historyWindowSize} 帧</span>
                    </div>
                    <div class="metrics-history-legend">
                        <span class="legend-item queue">队列</span>
                        <span class="legend-item vehicles">车辆</span>
                        <span class="legend-item congestion">拥堵</span>
                    </div>
                    <div class="metrics-history-chart">
                        <canvas class="metrics-history-canvas"></canvas>
                        <div class="metrics-history-empty">等待仿真数据</div>
                    </div>
                </div>
                
                <!-- 信号灯状态（仅信号灯路口） -->
                ${data.traffic_light ? this.renderTrafficLightSection(data.traffic_light) : ''}
                
                <!-- 入向车道 -->
                <div class="info-section">
                    <div class="section-title">
                        入向车道 (${Object.keys(data.incoming_lanes).length})
                    </div>
                    ${this.renderLaneList(data.incoming_lanes)}
                </div>
                
                <!-- 出向车道 -->
                <div class="info-section">
                    <div class="section-title">
                        出向车道 (${Object.keys(data.outgoing_lanes).length})
                    </div>
                    ${this.renderLaneList(data.outgoing_lanes)}
                </div>
                
                <!-- 相邻路口 -->
                ${data.connected_junctions.length > 0 ? `
                    <div class="info-section">
                        <div class="section-title">
                            相邻路口 (${data.connected_junctions.length})
                        </div>
                        <div class="lane-list">
                            ${data.connected_junctions.map(id => `
                                <div class="lane-item">
                                    <span class="lane-id">${id}</span>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                ` : ''}
                
                <!-- 统计信息 -->
                <div class="info-section">
                    <div class="section-title">累计统计</div>
                    <div class="info-grid">
                        <div class="info-item">
                            <div class="info-label">通过车辆总数</div>
                            <div class="info-value">${data.metrics.total_vehicles_passed}</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">总等待时间</div>
                            <div class="info-value">${data.metrics.total_waiting_time.toFixed(1)} s</div>
                        </div>
                        <div class="info-item">
                            <div class="info-label">最后更新</div>
                            <div class="info-value">${this.formatTimestamp(data.last_update_time)}</div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        this.panelContent.innerHTML = html;
        this.renderMetricsHistory(data.metrics_history, data.metrics);
    }

    /**
     * 绘制指标历史窗口，采用固定长度滚动视图。
     */
    renderMetricsHistory(history = [], currentMetrics = null) {
        if (!this.panelContent) return;

        const canvas = this.panelContent.querySelector('.metrics-history-canvas');
        if (!canvas) return;

        const empty = this.panelContent.querySelector('.metrics-history-empty');
        const samples = Array.isArray(history) ? history.slice(-this.historyWindowSize) : [];

        if (samples.length === 0 && currentMetrics) {
            samples.push({
                total_vehicles: currentMetrics.total_vehicles || 0,
                total_halting: currentMetrics.total_halting || 0,
                max_queue_length: currentMetrics.max_queue_length || 0,
                congestion_level: currentMetrics.congestion_level || 0
            });
        }

        if (empty) {
            empty.style.display = samples.length <= 1 ? 'flex' : 'none';
            empty.textContent = samples.length === 0 ? '等待仿真数据' : '等待更多历史帧';
        }

        const wrapper = canvas.parentElement;
        const rect = wrapper.getBoundingClientRect();
        const width = Math.max(280, rect.width || wrapper.clientWidth || 320);
        const height = Math.max(160, rect.height || 170);
        const dpr = window.devicePixelRatio || 1;

        canvas.width = Math.floor(width * dpr);
        canvas.height = Math.floor(height * dpr);
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;

        const ctx = canvas.getContext('2d');
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, width, height);

        this.drawHistoryGrid(ctx, width, height);
        if (samples.length === 0) return;

        const last = samples[samples.length - 1];
        this.updateHistoryLegend(last);

        const series = [
            {
                className: 'queue',
                values: samples.map(item => this.toMetricNumber(item.max_queue_length ?? item.total_halting)),
                color: '#2ee59d',
                fill: 'rgba(46, 229, 157, 0.12)'
            },
            {
                className: 'vehicles',
                values: samples.map(item => this.toMetricNumber(item.total_vehicles)),
                color: '#5dd7ff',
                fill: null
            },
            {
                className: 'congestion',
                values: samples.map(item => this.toMetricNumber(item.congestion_level) * 100),
                color: '#ffb454',
                fill: null,
                fixedMax: 100
            }
        ];

        series.forEach(item => this.drawHistorySeries(ctx, width, height, item));
    }

    drawHistoryGrid(ctx, width, height) {
        const padding = { left: 34, right: 12, top: 12, bottom: 24 };
        const chartWidth = width - padding.left - padding.right;
        const chartHeight = height - padding.top - padding.bottom;

        ctx.save();
        ctx.strokeStyle = 'rgba(80, 112, 119, 0.15)';
        ctx.lineWidth = 1;

        for (let i = 0; i <= 4; i++) {
            const y = padding.top + (chartHeight / 4) * i;
            ctx.beginPath();
            ctx.moveTo(padding.left, y);
            ctx.lineTo(padding.left + chartWidth, y);
            ctx.stroke();
        }

        for (let i = 0; i <= 6; i++) {
            const x = padding.left + (chartWidth / 6) * i;
            ctx.beginPath();
            ctx.moveTo(x, padding.top);
            ctx.lineTo(x, padding.top + chartHeight);
            ctx.stroke();
        }

        ctx.fillStyle = 'rgba(65, 93, 99, 0.64)';
        ctx.font = '11px "Segoe UI", sans-serif';
        ctx.fillText('高', 9, padding.top + 5);
        ctx.fillText('低', 9, padding.top + chartHeight);
        ctx.restore();
    }

    drawHistorySeries(ctx, width, height, series) {
        const values = series.values;
        if (!values.length) return;

        const padding = { left: 34, right: 12, top: 12, bottom: 24 };
        const chartWidth = width - padding.left - padding.right;
        const chartHeight = height - padding.top - padding.bottom;
        const maxValue = Math.max(series.fixedMax || 0, ...values, 1);
        const count = Math.max(values.length - 1, 1);

        const points = values.map((value, index) => {
            const x = padding.left + (chartWidth * index) / count;
            const y = padding.top + chartHeight * (1 - Math.min(value / maxValue, 1));
            return { x, y };
        });

        ctx.save();
        ctx.lineWidth = series.className === 'queue' ? 2.4 : 1.7;
        ctx.strokeStyle = series.color;
        ctx.shadowColor = series.color;
        ctx.shadowBlur = series.className === 'queue' ? 8 : 3;
        ctx.beginPath();
        points.forEach((point, index) => {
            if (index === 0) {
                ctx.moveTo(point.x, point.y);
            } else {
                ctx.lineTo(point.x, point.y);
            }
        });
        ctx.stroke();
        ctx.shadowBlur = 0;

        if (series.fill && points.length > 1) {
            ctx.lineTo(points[points.length - 1].x, padding.top + chartHeight);
            ctx.lineTo(points[0].x, padding.top + chartHeight);
            ctx.closePath();
            ctx.fillStyle = series.fill;
            ctx.fill();
        }

        const last = points[points.length - 1];
        ctx.fillStyle = series.color;
        ctx.beginPath();
        ctx.arc(last.x, last.y, series.className === 'queue' ? 3.5 : 2.6, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
    }

    updateHistoryLegend(lastSample) {
        const values = {
            queue: this.toMetricNumber(lastSample.max_queue_length ?? lastSample.total_halting),
            vehicles: this.toMetricNumber(lastSample.total_vehicles),
            congestion: `${(this.toMetricNumber(lastSample.congestion_level) * 100).toFixed(0)}%`
        };

        Object.entries(values).forEach(([key, value]) => {
            const element = this.panelContent.querySelector(`.metrics-history-legend .${key}`);
            if (element) {
                const labelMap = {
                    queue: '队列',
                    vehicles: '车辆',
                    congestion: '拥堵'
                };
                element.textContent = `${labelMap[key]} ${value}`;
            }
        });
    }

    toMetricNumber(value) {
        const number = Number(value);
        return Number.isFinite(number) ? number : 0;
    }
    
    /**
     * 渲染信号灯状态部分
     */
    renderTrafficLightSection(trafficLight) {
        return `
            <div class="info-section">
                <div class="section-title">信号灯状态</div>
                <div class="info-grid">
                    <div class="info-item">
                        <div class="info-label">相位持续时间</div>
                        <div class="info-value">${trafficLight.phase_duration.toFixed(1)} s</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">下次切换时间</div>
                        <div class="info-value">${trafficLight.next_switch_time.toFixed(1)} s</div>
                    </div>
                </div>
                <div class="info-item" style="margin-top: 12px;">
                    <div class="info-label">相位状态</div>
                    <div class="phase-display">
                        ${this.renderPhaseState(trafficLight.phase_state)}
                    </div>
                </div>
            </div>
        `;
    }
    
    /**
     * 渲染相位状态灯
     */
    renderPhaseState(phaseState) {
        if (!phaseState) return '<span style="color: #888;">未知</span>';
        
        return Array.from(phaseState).map(char => {
            let lightClass = 'off';
            if (char === 'r' || char === 'R') lightClass = 'red';
            else if (char === 'y' || char === 'Y') lightClass = 'yellow';
            else if (char === 'g' || char === 'G') lightClass = 'green';
            
            return `<div class="phase-light ${lightClass}"></div>`;
        }).join('');
    }
    
    /**
     * 渲染车道列表
     */
    renderLaneList(lanes) {
        if (Object.keys(lanes).length === 0) {
            return '<div style="color: #888; font-size: 13px; padding: 8px;">无车道</div>';
        }
        
        return `
            <div class="lane-list">
                ${Object.values(lanes).map(lane => `
                    <div class="lane-item" data-lane-id="${lane.lane_id}">
                        <span class="lane-id">${lane.lane_id}</span>
                        <div class="lane-stats">
                            <span title="车辆数">🚗 ${lane.vehicle_count}</span>
                            <span title="平均速度(km/h)">⏱️ ${(lane.mean_speed * 3.6).toFixed(1)}</span>
                            <span title="占有率">📊 ${lane.occupancy.toFixed(1)}%</span>
                            ${lane.halting_count > 0 ? `<span title="停车数" style="color: #ff9800;">⏸️ ${lane.halting_count}</span>` : ''}
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }
    
    /**
     * 渲染占位符
     */
    renderPlaceholder() {
        this.panelTitle.textContent = '路口详情';
        this.panelContent.innerHTML = `
            <div class="panel-placeholder">
                <div class="placeholder-icon">🗺️</div>
                <p>点击地图上的路口查看详细信息</p>
            </div>
        `;
    }
    
    // ========== 辅助方法 ==========
    
    getControlModeText(mode) {
        const modes = {
            'auto': '🤖 自动',
            'manual': '👤 手动',
            'priority': '⚡ 优先'
        };
        return modes[mode] || mode;
    }
    
    getCongestionText(level) {
        if (level < 0.2) return '畅通';
        if (level < 0.4) return '缓慢';
        if (level < 0.6) return '拥堵';
        if (level < 0.8) return '严重拥堵';
        return '瘫痪';
    }
    
    getCongestionClass(level) {
        if (level < 0.2) return 'success';
        if (level < 0.6) return 'warning';
        return 'error';
    }
    
    formatTimestamp(timestamp) {
        const date = new Date(timestamp * 1000);
        return date.toLocaleTimeString('zh-CN');
    }
}
