"use client";

import React, { createContext, useContext, ReactNode } from 'react';
import { useWorkspaces } from './useWorkspaces';
import { Workspace } from '../types/data';

interface WorkspaceContextType {
  workspaces: Workspace[];
  currentWorkspaceId: string;
  loading: boolean;
  switchWorkspace: (id: string) => void;
  createWorkspace: (name: string, description?: string) => Promise<Workspace | null>;
  updateWorkspace: (id: string, name: string, description?: string) => Promise<boolean>;
  deleteWorkspace: (id: string) => Promise<boolean>;
  refreshWorkspaces: () => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceContextType | undefined>(undefined);

export const WorkspaceProvider = ({ children }: { children: ReactNode }) => {
  const workspaceState = useWorkspaces();
  return (
    <WorkspaceContext.Provider value={workspaceState}>
      {children}
    </WorkspaceContext.Provider>
  );
};

export const useWorkspaceContext = () => {
  const context = useContext(WorkspaceContext);
  if (context === undefined) {
    throw new Error('useWorkspaceContext must be used within a WorkspaceProvider');
  }
  return context;
};
