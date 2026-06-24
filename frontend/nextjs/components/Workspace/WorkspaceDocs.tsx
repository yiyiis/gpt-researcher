import React, { useState, useEffect, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { useWorkspaceContext } from '../../hooks/WorkspaceContext';
import { WorkspaceDocument } from '../../types/data';
import { formatDistanceToNow } from 'date-fns';

const WorkspaceDocs: React.FC = () => {
  const { currentWorkspaceId } = useWorkspaceContext();
  const [documents, setDocuments] = useState<WorkspaceDocument[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');

  const fetchDocs = useCallback(async () => {
    if (!currentWorkspaceId) return;
    try {
      const res = await fetch(`/api/workspaces/${currentWorkspaceId}/documents`);
      if (res.ok) {
        const data = await res.json();
        setDocuments(data.documents || []);
      }
    } catch (e) {
      console.error('加载文档失败', e);
    }
  }, [currentWorkspaceId]);

  useEffect(() => {
    fetchDocs();
  }, [fetchDocs]);

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      if (acceptedFiles.length === 0) return;
      setUploading(true);
      setError('');
      try {
        for (const file of acceptedFiles) {
          const formData = new FormData();
          formData.append('file', file);
          const res = await fetch(
            `/api/workspaces/${currentWorkspaceId}/documents`,
            { method: 'POST', body: formData }
          );
          if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error || `上传失败 (${res.status})`);
          }
        }
        await fetchDocs();
      } catch (e: any) {
        setError(e.message || '上传失败');
      } finally {
        setUploading(false);
      }
    },
    [currentWorkspaceId, fetchDocs]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop });

  const deleteDoc = async (docId: string) => {
    if (!confirm('确定删除这个文档吗？')) return;
    try {
      const res = await fetch(
        `/api/workspaces/${currentWorkspaceId}/documents?doc_id=${docId}`,
        { method: 'DELETE' }
      );
      if (res.ok) {
        setDocuments((prev) => prev.filter((d) => d.id !== docId));
      }
    } catch (e) {
      console.error('删除文档失败', e);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatTime = (ts: number) => {
    try {
      return formatDistanceToNow(new Date(ts), { addSuffix: true });
    } catch {
      return '';
    }
  };

  return (
    <div className="ws-docs-container">
      {/* 拖拽上传区 */}
      <div
        {...getRootProps()}
        className={`ws-upload-zone ${isDragActive ? 'drag-active' : ''} ${uploading ? 'uploading' : ''}`}
      >
        <input {...getInputProps()} />
        {uploading ? (
          <span className="ws-upload-text">上传中...</span>
        ) : isDragActive ? (
          <span className="ws-upload-text">松开以上传</span>
        ) : (
          <span className="ws-upload-text">
            <i className="fas fa-cloud-upload-alt" style={{ marginRight: 6 }} />
            拖拽文件到此，或点击选择
          </span>
        )}
      </div>

      {error && <div className="ws-doc-error">{error}</div>}

      {/* 文档列表 */}
      {documents.length === 0 ? (
        !uploading && (
          <p className="ws-doc-empty">此工作区暂无文档</p>
        )
      ) : (
        <ul className="ws-doc-list">
          {documents.map((doc) => (
            <li key={doc.id} className="ws-doc-item">
              <div className="ws-doc-info">
                <div className="ws-doc-name">
                  <i className="fas fa-file-alt ws-doc-icon" />
                  <span title={doc.filename}>{doc.filename}</span>
                </div>
                <div className="ws-doc-meta">
                  {formatSize(doc.fileSize)} · {formatTime(doc.uploadedAt)}
                </div>
              </div>
              <button
                className="ws-doc-delete"
                onClick={() => deleteDoc(doc.id)}
                title="删除"
              >
                <i className="fas fa-trash" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default WorkspaceDocs;
