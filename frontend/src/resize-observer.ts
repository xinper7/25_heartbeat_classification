// Deliver size-driven layout changes after the browser's observer notification phase.
// This also covers third-party inputs/tables that synchronously write layout in callbacks.
const NativeResizeObserver = window.ResizeObserver;
if (NativeResizeObserver) {
  window.ResizeObserver = class extends NativeResizeObserver {
    private pending = new Map<Element, ResizeObserverEntry>();
    private frame: number | undefined;
    constructor(callback: ResizeObserverCallback) {
      super((entries) => {
        entries.forEach((entry) => this.pending.set(entry.target, entry));
        if (this.frame !== undefined) return;
        this.frame = requestAnimationFrame(() => {
          this.frame = undefined;
          const batch = [...this.pending.values()];
          this.pending.clear();
          if (batch.length) callback(batch, this);
        });
      });
    }
    unobserve(target: Element) {
      this.pending.delete(target);
      super.unobserve(target);
    }
    disconnect() {
      super.disconnect();
      this.pending.clear();
      if (this.frame !== undefined) cancelAnimationFrame(this.frame);
      this.frame = undefined;
    }
  };
}
export {};
