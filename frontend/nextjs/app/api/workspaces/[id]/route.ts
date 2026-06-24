import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_GPTR_API_URL || 'http://localhost:8000';

// 更新工作区（重命名/改描述）
export async function PUT(request: Request, { params }: { params: { id: string } }) {
  try {
    const body = await request.json();
    const response = await fetch(`${BACKEND_URL}/api/workspaces/${params.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: `Error ${response.status}` }));
      return NextResponse.json({ error: err.detail }, { status: response.status });
    }
    const data = await response.json();
    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error('PUT /api/workspaces/[id] - proxy error:', error);
    return NextResponse.json({ error: 'Failed to connect to backend' }, { status: 500 });
  }
}

// 删除工作区
export async function DELETE(_request: Request, { params }: { params: { id: string } }) {
  try {
    const response = await fetch(`${BACKEND_URL}/api/workspaces/${params.id}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: `Error ${response.status}` }));
      return NextResponse.json({ error: err.detail }, { status: response.status });
    }
    const data = await response.json();
    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error('DELETE /api/workspaces/[id] - proxy error:', error);
    return NextResponse.json({ error: 'Failed to connect to backend' }, { status: 500 });
  }
}
