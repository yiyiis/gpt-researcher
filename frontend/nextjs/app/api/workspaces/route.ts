import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_GPTR_API_URL || 'http://localhost:8000';

// 列出所有工作区
export async function GET() {
  try {
    const response = await fetch(`${BACKEND_URL}/api/workspaces`);
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: `Error ${response.status}` }));
      return NextResponse.json({ error: err.detail }, { status: response.status });
    }
    const data = await response.json();
    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error('GET /api/workspaces - proxy error:', error);
    return NextResponse.json({ error: 'Failed to connect to backend' }, { status: 500 });
  }
}

// 创建工作区
export async function POST(request: Request) {
  try {
    const body = await request.json();
    const response = await fetch(`${BACKEND_URL}/api/workspaces`, {
      method: 'POST',
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
    console.error('POST /api/workspaces - proxy error:', error);
    return NextResponse.json({ error: 'Failed to connect to backend' }, { status: 500 });
  }
}
