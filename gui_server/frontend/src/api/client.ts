import { getRealApi, type PywebviewApi } from './pywebview'
import { mockApi } from './mock'

let apiPromise: Promise<PywebviewApi> | null = null

/** Resolves to the real pywebview bridge when running inside the desktop
 * shell, or the in-memory mock when opened as a plain browser tab (dev). */
export function getApi(): Promise<PywebviewApi> {
  if (!apiPromise) {
    apiPromise = getRealApi().then((real) => {
      if (real) return real
      console.info('[api] window.pywebview not detected — using mock API (dev browser mode)')
      return mockApi
    })
  }
  return apiPromise
}
