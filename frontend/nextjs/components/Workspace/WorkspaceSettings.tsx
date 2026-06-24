import React, { useState, useEffect } from 'react';
import { useWorkspaceContext } from '../../hooks/WorkspaceContext';
import { formatDistanceToNow } from 'date-fns';

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

const WorkspaceSettings: React.FC<Props> = ({ isOpen, onClose }) => {
  const {
    workspaces,
    currentWorkspaceId,
    updateWorkspace,
    deleteWorkspace,
    switchWorkspace,
  } = useWorkspaceContext();

  const current = workspaces.find((w) => w.id === currentWorkspaceId);
  const isDefault = currentWorkspaceId === 'default';

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (current) {
      setName(current.name);
      setDescription(current.description || '');
      setConfirmDelete(false);
    }
  }, [current, isOpen]);

  if (!isOpen || !current) return null;

  const handleSave = async () => {
    if (!name.trim()) return;
    setSaving(true);
    await updateWorkspace(currentWorkspaceId, name.trim(), description.trim());
    setSaving(false);
    onClose();
  };

  const handleDelete = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    await deleteWorkspace(currentWorkspaceId);
    switchWorkspace('default');
    onClose();
  };

  return (
    <div className="ws-settings-overlay" onClick={onClose}>
      <div className="ws-settings-modal" onClick={(e) => e.stopPropagation()}>
        <div className="ws-settings-header">
          <h3>工作区设置</h3>
          <button className="ws-settings-close" onClick={onClose}>
            <i className="fas fa-times" />
          </button>
        </div>

        <div className="ws-settings-body">
          <div className="ws-settings-field">
            <label>名称</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="ws-settings-input"
              disabled={isDefault}
            />
            {isDefault && (
              <small className="ws-settings-hint">默认工作区不可重命名</small>
            )}
          </div>

          <div className="ws-settings-field">
            <label>描述</label>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="ws-settings-input"
              placeholder="工作区用途说明"
              disabled={isDefault}
            />
          </div>

          {current.created_at && (
            <div className="ws-settings-meta">
              创建于 {formatDistanceToNow(new Date(current.created_at), { addSuffix: true })}
            </div>
          )}
        </div>

        <div className="ws-settings-footer">
          {!isDefault && (
            <button
              className={`ws-settings-delete-btn ${confirmDelete ? 'confirm' : ''}`}
              onClick={handleDelete}
            >
              {confirmDelete ? '再次点击确认删除（含全部报告/文档）' : '删除工作区'}
            </button>
          )}
          <div style={{ flex: 1 }} />
          <button className="ws-settings-cancel-btn" onClick={onClose}>
            取消
          </button>
          <button
            className="ws-settings-save-btn"
            onClick={handleSave}
            disabled={saving || isDefault || !name.trim()}
          >
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default WorkspaceSettings;
