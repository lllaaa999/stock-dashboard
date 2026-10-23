import { useMarketStore } from '../store/useMarketStore';
import type { WSClientMessage, WSServerMessage } from '../types/market';

const HEARTBEAT_INTERVAL_MS = 30000; // 30s 心跳保活检测 (Heartbeat Ping/Pong)
const BASE_RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_DELAY_MS = 30000;

class MarketWebSocketClient {
  private ws: WebSocket | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private disconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts = 0;
  private manuallyClosed = false;

  /**
   * 构建 WebSocket 地址：生产云端 HTTPS 环境强制走 wss://，本地 HTTP 环境走 ws://
   */
  public getEndpointUrl(): string {
    if (typeof window === 'undefined') return 'ws://localhost:3000/ws';
    const isSecure = window.location.protocol === 'https:';
    const protocol = isSecure ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}/ws`;
  }

  public connect(): void {
    if (typeof window === 'undefined') return;
    if (this.disconnectTimer) {
      clearTimeout(this.disconnectTimer);
      this.disconnectTimer = null;
    }
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      this.manuallyClosed = false;
      return;
    }

    this.manuallyClosed = false;
    const store = useMarketStore.getState();
    store.setConnectionStatus(this.reconnectAttempts > 0 ? 'RECONNECTING' : 'CONNECTING');

    try {
      const url = this.getEndpointUrl();
      const socket = new WebSocket(url);
      this.ws = socket;

      socket.onopen = () => {
        if (this.manuallyClosed) {
          socket.close();
          return;
        }
        this.reconnectAttempts = 0;
        useMarketStore.getState().setConnectionStatus('CONNECTED');
        this.startHeartbeat();
      };

      socket.onmessage = (event: MessageEvent) => {
        try {
          const msg = JSON.parse(String(event.data)) as WSServerMessage;
          const state = useMarketStore.getState();

          if (msg.type === 'INIT_SNAPSHOT') {
            state.applyInitSnapshot(msg.quotes, msg.indices, msg.batchWindowMs, msg.serverTime);
          } else if (msg.type === 'SNAPSHOT_BATCH') {
            state.applySnapshotBatch(msg.quotes, msg.indices, msg.batchWindowMs, msg.serverTime);
          } else if (msg.type === 'PONG') {
            // 收到服务端 PONG 响应，连接健康
          }
        } catch {
          // 忽略格式异常帧
        }
      };

      socket.onclose = () => {
        this.stopHeartbeat();
        if (this.ws === socket) {
          this.ws = null;
        }
        if (!this.manuallyClosed) {
          this.scheduleReconnect();
        } else {
          useMarketStore.getState().setConnectionStatus('DISCONNECTED');
        }
      };

      socket.onerror = () => {
        // 错误后交由 onclose 统一触发指数退避重连
      };
    } catch {
      this.scheduleReconnect();
    }
  }

  /**
   * 指数退避重试 (Exponential Backoff with Jitter)
   * delay = min(30000, 1000 * 2^attempt) + random(0~400ms)
   */
  private scheduleReconnect(): void {
    if (this.manuallyClosed) return;
    this.clearReconnectTimer();

    useMarketStore.getState().setConnectionStatus('RECONNECTING');
    const expDelay = Math.min(
      MAX_RECONNECT_DELAY_MS,
      BASE_RECONNECT_DELAY_MS * Math.pow(2, this.reconnectAttempts)
    );
    const jitter = Math.floor(Math.random() * 400);
    const delay = expDelay + jitter;
    this.reconnectAttempts += 1;

    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, delay);
  }

  /**
   * 30 秒定时心跳保活 (Ping / Pong)
   */
  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      this.send({
        type: 'PING',
        timestamp: Date.now(),
      });
    }, HEARTBEAT_INTERVAL_MS);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  public send(message: WSClientMessage): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  public setServerBatchWindow(windowMs: number): void {
    const clamped = Math.max(100, Math.min(200, Math.round(windowMs)));
    useMarketStore.getState().setBatchWindowMs(clamped);
    this.send({
      type: 'SET_BATCH_WINDOW',
      windowMs: clamped,
    });
  }

  public disconnect(): void {
    if (this.disconnectTimer) {
      clearTimeout(this.disconnectTimer);
    }
    // 延迟关闭以兼容 React StrictMode 开发模式下的瞬间卸载重挂载，避免关闭处于 CONNECTING 状态的连接
    this.disconnectTimer = setTimeout(() => {
      this.manuallyClosed = true;
      this.stopHeartbeat();
      this.clearReconnectTimer();
      if (this.ws) {
        if (this.ws.readyState === WebSocket.OPEN) {
          this.ws.close();
        }
        this.ws = null;
      }
    }, 150);
  }
}

export const marketWsClient = new MarketWebSocketClient();
