import { useEffect, useRef, useState } from 'react'

interface UseWebSocketOptions {
  url: string
  enabled?: boolean
  onMessage?: (data: any) => void
  onOpen?: () => void
  onClose?: () => void
  onError?: (error: Event) => void
}

export function useWebSocket({
  url,
  enabled = true,
  onMessage,
  onOpen,
  onClose,
  onError,
}: UseWebSocketOptions) {
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>()

  useEffect(() => {
    if (!enabled) return

    const connect = () => {
      try {
        const ws = new WebSocket(url)
        wsRef.current = ws

        ws.onopen = () => {
          setIsConnected(true)
          onOpen?.()
        }

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            onMessage?.(data)
          } catch (error) {
            console.error('Failed to parse WebSocket message:', error)
          }
        }

        ws.onclose = () => {
          setIsConnected(false)
          onClose?.()

          // Reconnect after 5 seconds
          reconnectTimeoutRef.current = setTimeout(() => {
            connect()
          }, 5000)
        }

        ws.onerror = (error) => {
          onError?.(error)
        }
      } catch (error) {
        console.error('WebSocket connection error:', error)
      }
    }

    connect()

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      wsRef.current?.close()
    }
  }, [url, enabled])

  const sendMessage = (data: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }

  return { isConnected, sendMessage }
}
