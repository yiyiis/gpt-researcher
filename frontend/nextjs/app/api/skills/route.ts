import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_GPTR_API_URL || 'http://localhost:8000';

// 列出所有 skill
export async function GET() {
  try {
    const response = await fetch(`${BACKEND_URL}/api/skills`);
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: `Error ${response.status}` }));
      return NextResponse.json({ error: err.detail }, { status: response.status });
    }
    const data = await response.json();
    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error('GET /api/skills - proxy error:', error);
    return NextResponse.json({ error: 'Failed to connect to backend' }, { status: 500 });
  }
}

// 删除 skill（通过 ?name= 或 ?file= 查询参数）
export async function DELETE(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const queryString = searchParams.toString();
    const response = await fetch(`${BACKEND_URL}/api/skills?${queryString}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: `Error ${response.status}` }));
      return NextResponse.json({ error: err.detail }, { status: response.status });
    }
    const data = await response.json();
    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error('DELETE /api/skills - proxy error:', error);
    return NextResponse.json({ error: 'Failed to connect to backend' }, { status: 500 });
  }
}
