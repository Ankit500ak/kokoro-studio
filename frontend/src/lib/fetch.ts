const DEFAULT_TIMEOUT = 10000

export async function fetchWithTimeout(
  url: string | URL | Request,
  init?: RequestInit & { timeout?: number }
): Promise<Response> {
  const { timeout = DEFAULT_TIMEOUT, ...fetchInit } = init ?? {}
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    const response = await fetch(url, { ...fetchInit, signal: controller.signal })
    return response
  } finally {
    clearTimeout(timer)
  }
}
