import React, { useState, useEffect } from 'react';
import { MCPConfig } from '@/types/data';

interface MCPSelectorProps {
  mcpEnabled: boolean;
  mcpConfigs: MCPConfig[];
  onMCPChange: (enabled: boolean, configs: MCPConfig[]) => void;
}

// config.json 服务的展示信息（来自 /api/mcp-servers，不含密钥）
interface ConfigServer {
  name: string;
  description: string;
  enabled: boolean;
}

// 添加/编辑表单的连接类型选项
type ConnType = 'streamable_http' | 'websocket' | 'stdio';
const CONN_LABELS: Record<ConnType, string> = {
  streamable_http: 'HTTP',
  websocket: 'SSE / WebSocket',
  stdio: 'stdio (本地进程)',
};

// 根据 config 判断展示用的连接类型
const inferType = (c: MCPConfig): ConnType => {
  if (c.connection_type) {
    if (c.connection_type === 'stdio') return 'stdio';
    if (c.connection_type === 'websocket') return 'websocket';
    return 'streamable_http';
  }
  if (c.connection_url) {
    if (c.connection_url.startsWith('ws')) return 'websocket';
    return 'streamable_http';
  }
  if (c.command) return 'stdio';
  return 'streamable_http';
};

const MCPSelector: React.FC<MCPSelectorProps> = ({
  mcpEnabled,
  mcpConfigs,
  onMCPChange,
}) => {
  const [enabled, setEnabled] = useState(mcpEnabled);
  // 自定义服务器（用户在前端添加的，通过 mcp_configs 传给后端）
  const [configs, setConfigs] = useState<MCPConfig[]>(mcpConfigs || []);
  // config.json 里的服务（从后端 API 加载，只读展示）
  const [configServers, setConfigServers] = useState<ConfigServer[]>([]);
  const [loadingServers, setLoadingServers] = useState(true);
  const [showInfoModal, setShowInfoModal] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editIndex, setEditIndex] = useState<number | null>(null);

  // 添加/编辑表单状态
  const [fName, setFName] = useState('');
  const [fDesc, setFDesc] = useState('');
  const [fType, setFType] = useState<ConnType>('streamable_http');
  const [fUrl, setFUrl] = useState('');
  const [fHeaders, setFHeaders] = useState('');
  const [fCommand, setFCommand] = useState('');
  const [fArgs, setFArgs] = useState('');
  const [fEnv, setFEnv] = useState('');
  const [formError, setFormError] = useState('');

  // 同步 props
  useEffect(() => {
    setEnabled(mcpEnabled);
  }, [mcpEnabled]);

  useEffect(() => {
    setConfigs(mcpConfigs || []);
  }, [mcpConfigs]);

  // 从后端 API 加载 config.json 的 MCP 服务（只读展示）
  useEffect(() => {
    const loadServers = async () => {
      try {
        const backendUrl =
          process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
        const res = await fetch(`${backendUrl}/api/mcp-servers`);
        if (res.ok) {
          const data = await res.json();
          setConfigServers(data.servers || []);
        }
      } catch (e) {
        console.error('[MCP] 加载 config.json 服务失败:', e);
      } finally {
        setLoadingServers(false);
      }
    };
    loadServers();
  }, []);

  // 统一回调：把当前内部状态透传给父级
  const emit = (newEnabled: boolean, newConfigs: MCPConfig[]) => {
    onMCPChange(newEnabled, newConfigs);
  };

  const handleEnabledChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = e.target.checked;
    setEnabled(v);
    emit(v, configs);
  };

  // 切换单个自定义服务器的启用状态
  const toggleServer = (idx: number) => {
    const next = configs.map((c, i) =>
      i === idx ? { ...c, enabled: !c.enabled } : c
    );
    setConfigs(next);
    if (enabled) emit(enabled, next);
  };

  // 删除一个自定义服务器
  const removeServer = (idx: number) => {
    const next = configs.filter((_, i) => i !== idx);
    setConfigs(next);
    if (enabled) emit(enabled, next);
  };

  // 打开添加表单
  const openAdd = () => {
    setEditIndex(null);
    setFName('');
    setFDesc('');
    setFType('streamable_http');
    setFUrl('');
    setFHeaders('');
    setFCommand('');
    setFArgs('');
    setFEnv('');
    setFormError('');
    setShowAddModal(true);
  };

  // 打开编辑表单
  const openEdit = (idx: number) => {
    const c = configs[idx];
    setEditIndex(idx);
    setFName(c.name || '');
    setFDesc(c.description || '');
    setFType(inferType(c));
    setFUrl(c.connection_url || '');
    setFHeaders(
      c.connection_headers ? JSON.stringify(c.connection_headers, null, 2) : ''
    );
    setFCommand(c.command || '');
    setFArgs((c.args || []).join(', '));
    setFEnv(
      Object.entries(c.env || {})
        .map(([k, v]) => `${k}=${v}`)
        .join('\n')
    );
    setFormError('');
    setShowAddModal(true);
  };

  // 保存添加/编辑
  const saveServer = () => {
    setFormError('');
    if (!fName.trim()) {
      setFormError('请填写服务器名称');
      return;
    }
    const cfg: MCPConfig = {
      name: fName.trim(),
      description: fDesc.trim() || undefined,
      connection_type: fType,
      enabled: editIndex === null ? true : configs[editIndex]?.enabled ?? true,
    };

    if (fType === 'stdio') {
      if (!fCommand.trim()) {
        setFormError('stdio 类型需要填写启动命令');
        return;
      }
      cfg.command = fCommand.trim();
      cfg.args = fArgs
        .split(',')
        .map((a) => a.trim())
        .filter(Boolean);
      const envObj: Record<string, string> = {};
      fEnv.split('\n').forEach((line) => {
        const t = line.trim();
        if (!t) return;
        const ei = t.indexOf('=');
        if (ei > 0) envObj[t.slice(0, ei).trim()] = t.slice(ei + 1).trim();
      });
      if (Object.keys(envObj).length) cfg.env = envObj;
    } else {
      if (!fUrl.trim()) {
        setFormError(`${CONN_LABELS[fType]} 类型需要填写连接 URL`);
        return;
      }
      cfg.connection_url = fUrl.trim();
      if (fHeaders.trim()) {
        try {
          const parsed = JSON.parse(fHeaders);
          if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
            cfg.connection_headers = parsed;
          } else {
            throw new Error('Headers 必须是 JSON 对象');
          }
        } catch (e: any) {
          setFormError(`Headers JSON 无效: ${e.message}`);
          return;
        }
      }
    }

    let next: MCPConfig[];
    if (editIndex === null) {
      next = [...configs, cfg];
    } else {
      next = configs.map((c, i) => (i === editIndex ? cfg : c));
    }
    setConfigs(next);
    setShowAddModal(false);
    if (enabled) emit(enabled, next);
  };

  return (
    <div className="form-group">
      <div className="settings mcp-section">
        <div className="settings mcp-header">
          <label className="agent_question">
            <input
              type="checkbox"
              className="settings mcp-toggle"
              checked={enabled}
              onChange={handleEnabledChange}
            />
            启用 MCP（模型上下文协议）
          </label>
          <button
            type="button"
            className="settings mcp-info-btn"
            onClick={() => setShowInfoModal(true)}
            title="了解 MCP"
          >
            ℹ️
          </button>
        </div>
        <small
          className="text-muted"
          style={{
            color: 'rgba(255, 255, 255, 0.6)',
            fontSize: '0.85rem',
            marginBottom: '15px',
            display: 'block',
          }}
        >
          通过 MCP 服务器连接外部工具和数据源。勾选下方服务器以决定本次研究是否使用。
        </small>

        {/* 服务器列表（总开关开启时显示） */}
        {enabled && (
          <div className="settings mcp-config-section">
            {/* (1) config.json 的内置服务（只读，来自后端） */}
            <div className="settings mcp-list-header">
              <span className="agent_question" style={{ fontSize: '1rem' }}>
                内置 MCP 服务
              </span>
              <small
                className="text-muted"
                style={{ color: 'rgba(255,255,255,0.45)', fontSize: '0.78rem' }}
              >
                来自 config.json
              </small>
            </div>
            <small
              className="text-muted"
              style={{
                color: 'rgba(255,255,255,0.5)',
                fontSize: '0.8rem',
                display: 'block',
                marginBottom: '8px',
              }}
            >
              启用 MCP 后，下面标记为「已启用」的内置服务会自动生效（在 config.json 中管理开关）。
            </small>

            {loadingServers ? (
              <small
                className="text-muted"
                style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.85rem' }}
              >
                正在加载...
              </small>
            ) : configServers.length === 0 ? (
              <small
                className="text-muted"
                style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.85rem' }}
              >
                config.json 中未配置 MCP 服务
              </small>
            ) : (
              <div className="settings mcp-server-list">
                {configServers.map((s) => (
                  <div
                    key={s.name}
                    className={`settings mcp-server-card ${s.enabled ? 'on' : 'off'}`}
                  >
                    <div className="settings mcp-server-check" style={{ cursor: 'default' }}>
                      <span className="settings mcp-lock-icon" title="在 config.json 中管理">
                        <i className={`fas ${s.enabled ? 'fa-check-circle' : 'fa-circle'}`}></i>
                      </span>
                      <div className="settings mcp-server-info">
                        <div className="settings mcp-server-name">
                          {s.name}
                          <span className="settings mcp-type-badge streamable_http">HTTP</span>
                          {s.enabled && (
                            <span className="settings mcp-status-tag">已启用</span>
                          )}
                        </div>
                        {s.description && (
                          <small
                            className="text-muted"
                            style={{
                              color: 'rgba(255,255,255,0.55)',
                              fontSize: '0.8rem',
                            }}
                          >
                            {s.description}
                          </small>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* (2) 自定义服务（用户添加的） */}
            <div className="settings mcp-list-header" style={{ marginTop: '18px' }}>
              <span className="agent_question" style={{ fontSize: '1rem' }}>
                自定义 MCP 服务
              </span>
              <button
                type="button"
                className="settings preset-btn"
                onClick={openAdd}
              >
                <i className="fas fa-plus"></i> 添加服务器
              </button>
            </div>

            {configs.length === 0 ? (
              <small
                className="text-muted"
                style={{
                  color: 'rgba(255, 255, 255, 0.5)',
                  fontSize: '0.85rem',
                  display: 'block',
                  padding: '6px 0',
                }}
              >
                暂无自定义服务器，点击「添加服务器」创建。
              </small>
            ) : (
              <div className="settings mcp-server-list">
                {configs.map((c, idx) => {
                  const t = inferType(c);
                  const isEnabled = c.enabled ?? true;
                  return (
                    <div
                      key={`${c.name}-${idx}`}
                      className={`settings mcp-server-card ${isEnabled ? 'on' : 'off'}`}
                    >
                      <label className="settings mcp-server-check">
                        <input
                          type="checkbox"
                          className="settings mcp-toggle"
                          checked={isEnabled}
                          onChange={() => toggleServer(idx)}
                        />
                        <div className="settings mcp-server-info">
                          <div className="settings mcp-server-name">
                            {c.name}
                            <span className={`settings mcp-type-badge ${t}`}>
                              {CONN_LABELS[t]}
                            </span>
                          </div>
                          {c.description && (
                            <small
                              className="text-muted"
                              style={{
                                color: 'rgba(255,255,255,0.55)',
                                fontSize: '0.8rem',
                              }}
                            >
                              {c.description}
                            </small>
                          )}
                          <small
                            className="settings mcp-server-url"
                            title={c.connection_url || c.command}
                          >
                            {c.connection_url || c.command
                              ? c.connection_url || `${c.command} ${(c.args || []).join(' ')}`
                              : ''}
                          </small>
                        </div>
                      </label>
                      <div className="settings mcp-server-actions">
                        <button
                          type="button"
                          className="settings mcp-icon-btn"
                          title="编辑"
                          onClick={() => openEdit(idx)}
                        >
                          <i className="fas fa-pen"></i>
                        </button>
                        <button
                          type="button"
                          className="settings mcp-icon-btn danger"
                          title="删除"
                          onClick={() => removeServer(idx)}
                        >
                          <i className="fas fa-trash"></i>
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* 添加 / 编辑表单弹窗 */}
        {showAddModal && (
          <div className="settings mcp-info-modal visible">
            <div className="settings mcp-info-content">
              <button
                className="settings mcp-info-close"
                onClick={() => setShowAddModal(false)}
              >
                <i className="fas fa-times"></i>
              </button>
              <h3>{editIndex === null ? '添加 MCP 服务器' : '编辑 MCP 服务器'}</h3>
              <p>填写新的 MCP 配置，保存后返回列表。</p>

              <div className="settings mcp-field">
                <label className="agent_question">名称 *</label>
                <input
                  className="settings mcp-input"
                  value={fName}
                  onChange={(e) => setFName(e.target.value)}
                  placeholder="例如：tavily-search"
                />
              </div>

              <div className="settings mcp-field">
                <label className="agent_question">描述（选填）</label>
                <input
                  className="settings mcp-input"
                  value={fDesc}
                  onChange={(e) => setFDesc(e.target.value)}
                  placeholder="例如：Tavily 网页搜索"
                />
              </div>

              <div className="settings mcp-field">
                <label className="agent_question">连接类型</label>
                <select
                  className="form-control-static"
                  value={fType}
                  onChange={(e) => setFType(e.target.value as ConnType)}
                >
                  <option value="streamable_http">HTTP（远程）</option>
                  <option value="websocket">SSE / WebSocket</option>
                  <option value="stdio">stdio（本地进程，如 GitHub / 文件系统）</option>
                </select>
              </div>

              {fType !== 'stdio' ? (
                <>
                  <div className="settings mcp-field">
                    <label className="agent_question">连接 URL *</label>
                    <input
                      className="settings mcp-input"
                      value={fUrl}
                      onChange={(e) => setFUrl(e.target.value)}
                      placeholder="https://example.com/mcp"
                    />
                  </div>
                  <div className="settings mcp-field">
                    <label className="agent_question">请求头 Headers（JSON，选填）</label>
                    <textarea
                      className="settings mcp-config-textarea"
                      rows={4}
                      placeholder={'{\n  "Authorization": "Bearer 你的key"\n}'}
                      value={fHeaders}
                      onChange={(e) => setFHeaders(e.target.value)}
                      style={{ minHeight: '90px' }}
                    />
                  </div>
                </>
              ) : (
                <>
                  <div className="settings mcp-field">
                    <label className="agent_question">启动命令 *</label>
                    <input
                      className="settings mcp-input"
                      value={fCommand}
                      onChange={(e) => setFCommand(e.target.value)}
                      placeholder="例如：npx"
                    />
                  </div>
                  <div className="settings mcp-field">
                    <label className="agent_question">参数（逗号分隔）</label>
                    <input
                      className="settings mcp-input"
                      value={fArgs}
                      onChange={(e) => setFArgs(e.target.value)}
                      placeholder="例如：-y, @modelcontextprotocol/server-github"
                    />
                  </div>
                  <div className="settings mcp-field">
                    <label className="agent_question">环境变量（每行 KEY=value）</label>
                    <textarea
                      className="settings mcp-config-textarea"
                      rows={3}
                      placeholder={'GITHUB_PERSONAL_ACCESS_TOKEN=your_token'}
                      value={fEnv}
                      onChange={(e) => setFEnv(e.target.value)}
                      style={{ minHeight: '70px' }}
                    />
                  </div>
                </>
              )}

              {formError && (
                <div
                  style={{
                    color: '#dc3545',
                    fontSize: '0.85rem',
                    margin: '8px 0',
                  }}
                >
                  {formError}
                </div>
              )}

              <div className="settings mcp-form-actions">
                <button
                  type="button"
                  className="settings preset-btn"
                  onClick={() => setShowAddModal(false)}
                >
                  取消
                </button>
                <button
                  type="button"
                  className="settings preset-btn selected"
                  onClick={saveServer}
                >
                  保存
                </button>
              </div>
            </div>
          </div>
        )}

        {/* MCP Info Modal */}
        {showInfoModal && (
          <div className="settings mcp-info-modal visible">
            <div className="settings mcp-info-content">
              <button
                className="settings mcp-info-close"
                onClick={() => setShowInfoModal(false)}
              >
                <i className="fas fa-times"></i>
              </button>
              <h3>Model Context Protocol (MCP)</h3>
              <p>
                MCP enables GPT Researcher to connect with external tools and data sources through a standardized protocol.
              </p>

              <h4 className="highlight">两类服务：</h4>
              <ul>
                <li><span className="highlight">内置服务：</span>来自 config.json，由后端统一管理，启用 MCP 后自动生效</li>
                <li><span className="highlight">自定义服务：</span>点「添加服务器」自行配置，可勾选/编辑/删除</li>
              </ul>

              <h4 className="highlight">支持两种连接：</h4>
              <ul>
                <li><span className="highlight">HTTP（远程）：</span>如智谱 MCP，填 URL + Headers</li>
                <li><span className="highlight">stdio（本地）：</span>如 GitHub/文件系统，填命令 + 参数</li>
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default MCPSelector;
