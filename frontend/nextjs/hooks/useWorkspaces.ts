import { useState, useEffect, useCallback } from 'react';
import { Workspace } from '../types/data';

const STORAGE_KEY = 'currentWorkspaceId';

export const useWorkspaces = () => {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [currentWorkspaceId, setCurrentWorkspaceId] = useState<string>('default');
  const [loading, setLoading] = useState(true);

  // 加载工作区列表
  const fetchWorkspaces = useCallback(async () => {
    try {
      const response = await fetch('/api/workspaces');
      if (response.ok) {
        const data = await response.json();
        const list: Workspace[] = data.workspaces || [];
        setWorkspaces(list);
        // 恢复上次选中的工作区（localStorage 持久化）
        if (typeof window !== 'undefined') {
          const saved = localStorage.getItem(STORAGE_KEY);
          if (saved && list.some((w) => w.id === saved)) {
            setCurrentWorkspaceId(saved);
          } else if (list.length > 0) {
            setCurrentWorkspaceId(list[0].id);
          }
        }
      }
    } catch (error) {
      console.error('Error fetching workspaces:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchWorkspaces();
  }, [fetchWorkspaces]);

  // 切换当前工作区
  const switchWorkspace = useCallback((id: string) => {
    setCurrentWorkspaceId(id);
    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEY, id);
    }
  }, []);

  // 创建工作区
  const createWorkspace = useCallback(
    async (name: string, description: string = ''): Promise<Workspace | null> => {
      try {
        const response = await fetch('/api/workspaces', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, description }),
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        const ws = data.workspace;
        setWorkspaces((prev) => [...prev, ws]);
        // 创建后自动切换到新工作区
        switchWorkspace(ws.id);
        return ws;
      } catch (error) {
        console.error('Error creating workspace:', error);
        return null;
      }
    },
    [switchWorkspace]
  );

  // 重命名/更新工作区
  const updateWorkspace = useCallback(
    async (id: string, name: string, description?: string): Promise<boolean> => {
      try {
        const response = await fetch(`/api/workspaces/${id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, description }),
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        setWorkspaces((prev) =>
          prev.map((w) => (w.id === id ? data.workspace : w))
        );
        return true;
      } catch (error) {
        console.error('Error updating workspace:', error);
        return false;
      }
    },
    []
  );

  // 删除工作区
  const deleteWorkspace = useCallback(
    async (id: string): Promise<boolean> => {
      try {
        const response = await fetch(`/api/workspaces/${id}`, { method: 'DELETE' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        setWorkspaces((prev) => prev.filter((w) => w.id !== id));
        // 删的不是当前工作区就不用切
        if (currentWorkspaceId === id) {
          switchWorkspace('default');
        }
        return true;
      } catch (error) {
        console.error('Error deleting workspace:', error);
        return false;
      }
    },
    [currentWorkspaceId, switchWorkspace]
  );

  return {
    workspaces,
    currentWorkspaceId,
    loading,
    switchWorkspace,
    createWorkspace,
    updateWorkspace,
    deleteWorkspace,
    refreshWorkspaces: fetchWorkspaces,
  };
};
