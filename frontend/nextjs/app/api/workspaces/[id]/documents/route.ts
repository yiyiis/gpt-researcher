import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_GPTR_API_URL || 'http://localhost:8000';

// 列出工作区文档
export async function GET(_request: Request, { params }: { params: { id: string } }) {
  try {
    const response = await fetch(`${BACKEND_URL}/api/workspaces/${params.id}/documents`);
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: `Error ${response.status}` }));
      return NextResponse.json({ error: err.detail }, { status: response.status });
    }
    const data = await response.json();
    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error('GET documents - proxy error:', error);
    return NextResponse.json({ error: 'Failed to connect to backend' }, { status: 500 });
  }
}

// 上传文档到工作区（multipart 透传）
export async function POST(request: Request, { params }: { params: { id: string } }) {
  try {
    const formData = await request.formData();
    const response = await fetch(`${BACKEND_URL}/api/workspaces/${params.id}/documents`, {
      method: 'POST',
      body: formData,
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: `Error ${response.status}` }));
      return NextResponse.json({ error: err.detail }, { status: response.status });
    }
    const data = await response.json();
    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error('POST documents - proxy error:', error);
    return NextResponse.json({ error: 'Failed to connect to backend' }, { status: 500 });
  }
}

// 删除工作区文档（通过 ?doc_id= 查询参数）
export async function DELETE(request: Request, { params }: { params: { id: string } }) {
  try {
    const { searchParams } = new URL(request.url);
    const docId = searchParams.get('doc_id');
    if (!docId) {
      return NextResponse.json({ error: 'doc_id is required' }, { status: 400 });
    }
    const response = await fetch(
      `${BACKEND_URL}/api/workspaces/${params.id}/documents/${docId}`,
      { method: 'DELETE' }
    );
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: `Error ${response.status}` }));
      return NextResponse.json({ error: err.detail }, { status: response.status });
    }
    const data = await response.json();
    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error('DELETE documents - proxy error:', error);
    return NextResponse.json({ error: 'Failed to connect to backend' }, { status: 500 });
  }
}
