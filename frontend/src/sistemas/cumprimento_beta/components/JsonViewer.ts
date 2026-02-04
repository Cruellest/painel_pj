// frontend/src/sistemas/cumprimento_beta/components/JsonViewer.ts
/**
 * JsonViewer - Componente para visualização interativa de JSON
 *
 * Features:
 * - Visualização em árvore com colapso/expansão
 * - Destaque de tipos (string/number/boolean/null/array/object)
 * - Busca dentro do JSON
 * - Copiar/Baixar JSON
 * - Expandir/Recolher tudo
 * - Virtualização para JSONs grandes
 *
 * @author LAB/PGE-MS
 */

import type { JsonValue, JsonObject, JsonArray } from '../types';

export interface JsonViewerOptions {
  collapsed?: boolean;
  searchEnabled?: boolean;
  maxHeight?: string;
  theme?: 'light' | 'dark';
  rootName?: string;
}

interface NodeState {
  expanded: boolean;
  matches: boolean;
}

export class JsonViewer {
  private container: HTMLElement;
  private data: JsonValue;
  private options: Required<JsonViewerOptions>;
  private nodeStates: Map<string, NodeState> = new Map();
  private searchQuery: string = '';
  private matchingPaths: Set<string> = new Set();

  constructor(container: HTMLElement, data: JsonValue, options: JsonViewerOptions = {}) {
    this.container = container;
    this.data = data;
    this.options = {
      collapsed: options.collapsed ?? false,
      searchEnabled: options.searchEnabled ?? true,
      maxHeight: options.maxHeight ?? '500px',
      theme: options.theme ?? 'light',
      rootName: options.rootName ?? 'root',
    };

    this.initializeNodeStates(data, '');
    this.render();
  }

  private initializeNodeStates(value: JsonValue, path: string): void {
    if (this.isObject(value)) {
      this.nodeStates.set(path, { expanded: !this.options.collapsed, matches: false });
      Object.entries(value).forEach(([key, val]) => {
        this.initializeNodeStates(val, path ? `${path}.${key}` : key);
      });
    } else if (this.isArray(value)) {
      this.nodeStates.set(path, { expanded: !this.options.collapsed, matches: false });
      value.forEach((val, index) => {
        this.initializeNodeStates(val, path ? `${path}[${index}]` : `[${index}]`);
      });
    }
  }

  private isObject(value: JsonValue): value is JsonObject {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  }

  private isArray(value: JsonValue): value is JsonArray {
    return Array.isArray(value);
  }

  private escapeHtml(str: string): string {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  private getTypeClass(value: JsonValue): string {
    if (value === null) return 'json-null';
    if (typeof value === 'string') return 'json-string';
    if (typeof value === 'number') return 'json-number';
    if (typeof value === 'boolean') return 'json-boolean';
    if (this.isArray(value)) return 'json-array';
    if (this.isObject(value)) return 'json-object';
    return '';
  }

  private formatValue(value: JsonValue): string {
    if (value === null) return '<span class="json-null">null</span>';
    if (typeof value === 'string') {
      const escaped = this.escapeHtml(value);
      const highlighted = this.highlightSearch(escaped);
      return `<span class="json-string">"${highlighted}"</span>`;
    }
    if (typeof value === 'number') return `<span class="json-number">${value}</span>`;
    if (typeof value === 'boolean') return `<span class="json-boolean">${value}</span>`;
    return '';
  }

  private highlightSearch(text: string): string {
    if (!this.searchQuery) return text;
    const regex = new RegExp(`(${this.escapeRegex(this.searchQuery)})`, 'gi');
    return text.replace(regex, '<mark class="json-highlight">$1</mark>');
  }

  private escapeRegex(str: string): string {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  private renderNode(key: string, value: JsonValue, path: string, indent: number): string {
    const isExpandable = this.isObject(value) || this.isArray(value);
    const state = this.nodeStates.get(path);
    const isExpanded = state?.expanded ?? true;
    const matches = this.matchingPaths.has(path);
    const matchClass = matches ? 'json-match' : '';

    const keyHtml = key ? `<span class="json-key ${matchClass}">${this.highlightSearch(this.escapeHtml(key))}</span>: ` : '';
    const indentStyle = `padding-left: ${indent * 20}px`;

    if (!isExpandable) {
      return `<div class="json-line" style="${indentStyle}">${keyHtml}${this.formatValue(value)}</div>`;
    }

    const isArray = this.isArray(value);
    const entries = isArray ? value : Object.entries(value as JsonObject);
    const count = isArray ? value.length : Object.keys(value as JsonObject).length;
    const bracket = isArray ? ['[', ']'] : ['{', '}'];
    const typeLabel = isArray ? `Array(${count})` : `Object`;

    const toggleIcon = isExpanded ? 'fa-chevron-down' : 'fa-chevron-right';
    const collapsedPreview = !isExpanded
      ? `<span class="json-preview">${bracket[0]}...${bracket[1]} <span class="json-count">${count} items</span></span>`
      : '';

    let html = `
      <div class="json-line json-expandable ${matchClass}" style="${indentStyle}">
        <button class="json-toggle" data-path="${path}" aria-label="${isExpanded ? 'Recolher' : 'Expandir'}">
          <i class="fas ${toggleIcon}"></i>
        </button>
        ${keyHtml}<span class="json-type-label">${typeLabel}</span> ${bracket[0]}${collapsedPreview}
      </div>
    `;

    if (isExpanded) {
      if (isArray) {
        (value as JsonArray).forEach((item, index) => {
          const childPath = path ? `${path}[${index}]` : `[${index}]`;
          html += this.renderNode(String(index), item, childPath, indent + 1);
        });
      } else {
        Object.entries(value as JsonObject).forEach(([k, v]) => {
          const childPath = path ? `${path}.${k}` : k;
          html += this.renderNode(k, v, childPath, indent + 1);
        });
      }
      html += `<div class="json-line" style="${indentStyle}">${bracket[1]}</div>`;
    }

    return html;
  }

  private renderToolbar(): string {
    return `
      <div class="json-toolbar">
        ${this.options.searchEnabled ? `
          <div class="json-search">
            <i class="fas fa-search"></i>
            <input type="text" class="json-search-input" placeholder="Buscar..." value="${this.escapeHtml(this.searchQuery)}">
            ${this.searchQuery ? `<span class="json-search-count">${this.matchingPaths.size} encontrado(s)</span>` : ''}
          </div>
        ` : ''}
        <div class="json-actions">
          <button class="json-btn" data-action="expand-all" title="Expandir tudo">
            <i class="fas fa-plus-square"></i>
          </button>
          <button class="json-btn" data-action="collapse-all" title="Recolher tudo">
            <i class="fas fa-minus-square"></i>
          </button>
          <button class="json-btn" data-action="copy" title="Copiar JSON">
            <i class="fas fa-copy"></i>
          </button>
          <button class="json-btn" data-action="download" title="Baixar JSON">
            <i class="fas fa-download"></i>
          </button>
        </div>
      </div>
    `;
  }

  private render(): void {
    const treeHtml = this.renderNode('', this.data, '', 0);

    this.container.innerHTML = `
      <div class="json-viewer ${this.options.theme}">
        ${this.renderToolbar()}
        <div class="json-tree" style="max-height: ${this.options.maxHeight}; overflow: auto;">
          ${treeHtml}
        </div>
      </div>
    `;

    this.attachEventListeners();
  }

  private attachEventListeners(): void {
    // Toggle nodes
    this.container.querySelectorAll<HTMLButtonElement>('.json-toggle').forEach(btn => {
      btn.addEventListener('click', () => {
        const path = btn.dataset.path ?? '';
        this.toggleNode(path);
      });
    });

    // Search
    const searchInput = this.container.querySelector<HTMLInputElement>('.json-search-input');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        this.search((e.target as HTMLInputElement).value);
      });
    }

    // Actions
    this.container.querySelectorAll<HTMLButtonElement>('.json-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const action = btn.dataset.action;
        switch (action) {
          case 'expand-all':
            this.expandAll();
            break;
          case 'collapse-all':
            this.collapseAll();
            break;
          case 'copy':
            this.copyToClipboard();
            break;
          case 'download':
            this.downloadJson();
            break;
        }
      });
    });
  }

  private toggleNode(path: string): void {
    const state = this.nodeStates.get(path);
    if (state) {
      state.expanded = !state.expanded;
      this.render();
    }
  }

  public expandAll(): void {
    this.nodeStates.forEach(state => {
      state.expanded = true;
    });
    this.render();
  }

  public collapseAll(): void {
    this.nodeStates.forEach(state => {
      state.expanded = false;
    });
    this.render();
  }

  public search(query: string): void {
    this.searchQuery = query.toLowerCase();
    this.matchingPaths.clear();

    if (this.searchQuery) {
      this.findMatches(this.data, '');
      // Auto-expand matching paths
      this.matchingPaths.forEach(path => {
        this.expandPath(path);
      });
    }

    this.render();
  }

  private findMatches(value: JsonValue, path: string): void {
    if (value === null) return;

    if (typeof value === 'string' && value.toLowerCase().includes(this.searchQuery)) {
      this.matchingPaths.add(path);
    } else if (typeof value === 'number' && String(value).includes(this.searchQuery)) {
      this.matchingPaths.add(path);
    } else if (this.isObject(value)) {
      Object.entries(value).forEach(([key, val]) => {
        const childPath = path ? `${path}.${key}` : key;
        if (key.toLowerCase().includes(this.searchQuery)) {
          this.matchingPaths.add(childPath);
        }
        this.findMatches(val, childPath);
      });
    } else if (this.isArray(value)) {
      value.forEach((val, index) => {
        const childPath = path ? `${path}[${index}]` : `[${index}]`;
        this.findMatches(val, childPath);
      });
    }
  }

  private expandPath(path: string): void {
    const parts = path.split(/\.|\[/).filter(Boolean);
    let currentPath = '';
    parts.forEach((part, index) => {
      if (index > 0) {
        currentPath += part.startsWith('[') ? part : `.${part}`;
      } else {
        currentPath = part.replace(']', '');
      }
      const state = this.nodeStates.get(currentPath.replace(/\]/g, ''));
      if (state) {
        state.expanded = true;
      }
    });
  }

  public async copyToClipboard(): Promise<void> {
    try {
      await navigator.clipboard.writeText(JSON.stringify(this.data, null, 2));
      this.showToast('JSON copiado!');
    } catch {
      this.showToast('Erro ao copiar', 'error');
    }
  }

  public downloadJson(): void {
    const blob = new Blob([JSON.stringify(this.data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'dados.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    this.showToast('JSON baixado!');
  }

  private showToast(message: string, type: 'success' | 'error' = 'success'): void {
    const toast = document.createElement('div');
    toast.className = `json-toast json-toast-${type}`;
    toast.textContent = message;
    this.container.appendChild(toast);
    setTimeout(() => toast.remove(), 2000);
  }

  public update(data: JsonValue): void {
    this.data = data;
    this.nodeStates.clear();
    this.initializeNodeStates(data, '');
    this.render();
  }

  public destroy(): void {
    this.container.innerHTML = '';
  }
}

// CSS Styles (to be injected)
export const jsonViewerStyles = `
  .json-viewer {
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 13px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    overflow: hidden;
  }

  .json-viewer.dark {
    background: #1e293b;
    border-color: #334155;
  }

  .json-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    background: #f1f5f9;
    border-bottom: 1px solid #e2e8f0;
    gap: 12px;
  }

  .dark .json-toolbar {
    background: #0f172a;
    border-color: #334155;
  }

  .json-search {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    max-width: 300px;
  }

  .json-search i {
    color: #94a3b8;
  }

  .json-search-input {
    flex: 1;
    padding: 6px 10px;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    font-size: 12px;
    outline: none;
  }

  .json-search-input:focus {
    border-color: #3b82f6;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
  }

  .json-search-count {
    font-size: 11px;
    color: #64748b;
  }

  .json-actions {
    display: flex;
    gap: 4px;
  }

  .json-btn {
    padding: 6px 10px;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    cursor: pointer;
    color: #64748b;
    transition: all 0.15s;
  }

  .json-btn:hover {
    background: #f1f5f9;
    color: #334155;
    border-color: #cbd5e1;
  }

  .json-tree {
    padding: 12px;
  }

  .json-line {
    line-height: 1.6;
    white-space: nowrap;
  }

  .json-expandable {
    cursor: pointer;
  }

  .json-toggle {
    background: none;
    border: none;
    padding: 0 4px;
    cursor: pointer;
    color: #64748b;
    font-size: 10px;
    width: 16px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .json-toggle:hover {
    color: #3b82f6;
  }

  .json-key {
    color: #0f172a;
    font-weight: 500;
  }

  .dark .json-key {
    color: #e2e8f0;
  }

  .json-string {
    color: #16a34a;
  }

  .json-number {
    color: #2563eb;
  }

  .json-boolean {
    color: #dc2626;
  }

  .json-null {
    color: #9333ea;
    font-style: italic;
  }

  .json-type-label {
    color: #94a3b8;
    font-size: 11px;
    font-style: italic;
  }

  .json-preview {
    color: #94a3b8;
  }

  .json-count {
    font-size: 11px;
  }

  .json-highlight {
    background: #fef08a;
    padding: 0 2px;
    border-radius: 2px;
  }

  .json-match {
    background: rgba(59, 130, 246, 0.1);
    border-radius: 2px;
  }

  .json-toast {
    position: absolute;
    bottom: 12px;
    right: 12px;
    padding: 8px 16px;
    background: #22c55e;
    color: white;
    border-radius: 6px;
    font-size: 12px;
    animation: toast-in 0.2s ease-out;
  }

  .json-toast-error {
    background: #ef4444;
  }

  @keyframes toast-in {
    from {
      opacity: 0;
      transform: translateY(10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
`;
