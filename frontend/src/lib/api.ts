import ky, { HTTPError, NetworkError, TimeoutError } from 'ky';
import type { Options } from 'ky';
import type { Operation } from '../types.ts';

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '操作未完成，请重试';
}

type ApiOptions = Omit<Options, 'retry' | 'timeout' | 'credentials'>;
export interface ApiClient {
  (path: string, options: ApiOptions & { blob: true }): Promise<Blob>;
  <T = unknown>(path: string, options?: ApiOptions): Promise<T>;
}

export function createApi(onUnauthorized: () => void): ApiClient {
  const client = ky.create({
    credentials: 'same-origin',
    timeout: 12000,
    // Never replay a light command, scene creation or timer after a network failure.
    retry: 0,
  });
  async function request(path: string, options: ApiOptions & { blob: true }): Promise<Blob>;
  async function request<T = unknown>(path: string, options?: ApiOptions): Promise<T>;
  async function request<T = unknown>(
    path: string,
    options: ApiOptions & { blob?: boolean } = {},
  ): Promise<T | Blob> {
    const { blob, ...requestOptions } = options;
    try {
      const response = await client(`/api/v1${path}`, requestOptions);
      if (response.status === 204) return null as T;
      return blob ? response.blob() : response.json<T>();
    } catch (error) {
      if (error instanceof HTTPError) {
        if (error.response.status === 401 && path !== '/session') onUnauthorized();
        const data: unknown = error.data;
        const detail =
          data && typeof data === 'object' && 'detail' in data ? data.detail : undefined;
        throw new Error(
          Array.isArray(detail)
            ? '请检查输入的数值和格式'
            : typeof detail === 'string'
              ? detail
              : `请求未完成（${error.response.status}）`,
        );
      }
      if (
        error instanceof TimeoutError ||
        error instanceof NetworkError ||
        error instanceof TypeError ||
        (error instanceof Error && error.name === 'AbortError')
      )
        throw new Error('服务暂时无法连接，请检查部署设备和网络');
      throw error;
    }
  }
  return request;
}

export async function waitOperation(api: ApiClient, operation: Operation): Promise<Operation> {
  const terminal: Operation['status'][] = [
    'confirmed',
    'staged',
    'failed',
    'expired',
    'cancelled',
    'superseded',
  ];
  const deadline = Date.now() + 45000;
  while (!terminal.includes(operation.status)) {
    if (Date.now() > deadline) throw new Error('操作确认时间较长，请刷新查看实际灯光状态');
    await new Promise<void>((resolve) => setTimeout(resolve, 300));
    operation = await api<Operation>(`/operations/${operation.id}`);
  }
  if (!['confirmed', 'staged'].includes(operation.status))
    throw new Error(operation.message || '灯具操作未完成');
  return operation;
}
