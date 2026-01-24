// Generated from TypeScript - DO NOT EDIT DIRECTLY
// Source: src\sistemas\matriculas_confrontantes\components.ts
// Built at: 2026-01-24T19:56:06.799Z

"use strict";
(() => {
  // src/sistemas/matriculas_confrontantes/components.ts
  var BADGE_VARIANTS = {
    success: "bg-green-100 text-green-700",
    warning: "bg-yellow-100 text-yellow-700",
    info: "bg-blue-100 text-blue-700",
    error: "bg-red-100 text-red-700",
    neutral: "bg-gray-100 text-gray-700"
  };
  function Badge(text, variant = "info") {
    const classes = BADGE_VARIANTS[variant] || BADGE_VARIANTS.info;
    return `<span class="px-2 py-1 text-xs font-medium rounded-full ${classes}">${text}</span>`;
  }
  function Button({
    text,
    icon,
    variant = "primary",
    size = "md",
    onClick = ""
  }) {
    const variants = {
      primary: "bg-primary-600 text-white hover:bg-primary-700",
      secondary: "bg-gray-100 text-gray-700 hover:bg-gray-200",
      danger: "bg-red-50 text-red-600 hover:bg-red-100",
      ghost: "text-gray-600 hover:bg-gray-100"
    };
    const sizes = {
      sm: "px-2 py-1 text-xs",
      md: "px-3 py-1.5 text-sm",
      lg: "px-4 py-2 text-base"
    };
    const iconHtml = icon ? `<i class="fas fa-${icon}"></i>` : "";
    return `
    <button class="${sizes[size]} ${variants[variant]} rounded-lg transition-colors flex items-center gap-2" ${onClick ? `onclick="${onClick}"` : ""}>
      ${iconHtml}
      ${text || ""}
    </button>
  `;
  }
  function Card({ title, icon, content, footer = "" }) {
    return `
    <div class="bg-gray-50 rounded-lg p-4 shadow-sm border border-gray-100 hover:shadow-md transition-shadow">
      ${title ? `
        <div class="flex items-center gap-2 mb-3">
          ${icon ? `
            <div class="w-8 h-8 rounded-lg bg-primary-100 flex items-center justify-center">
              <i class="fas fa-${icon} text-primary-600 text-sm"></i>
            </div>
          ` : ""}
          <h3 class="font-medium text-gray-800">${title}</h3>
        </div>
      ` : ""}
      <div class="text-sm text-gray-600">
        ${content}
      </div>
      ${footer ? `
        <div class="mt-3 pt-3 border-t border-gray-200">
          ${footer}
        </div>
      ` : ""}
    </div>
  `;
  }
  function ProgressBar(value, size = "md") {
    const sizes = { sm: "h-1", md: "h-2", lg: "h-3" };
    let color = "bg-green-500";
    if (value < 90) color = "bg-yellow-500";
    if (value < 70) color = "bg-red-500";
    return `
    <div class="w-full ${sizes[size]} bg-gray-200 rounded-full overflow-hidden">
      <div class="${sizes[size]} ${color} rounded-full transition-all" style="width: ${value}%"></div>
    </div>
  `;
  }
  function IconButton({
    icon,
    title = "",
    variant = "ghost",
    onClick = ""
  }) {
    const variants = {
      ghost: "text-gray-400 hover:text-gray-600 hover:bg-gray-100",
      primary: "text-gray-400 hover:text-primary-600 hover:bg-primary-50",
      danger: "text-gray-400 hover:text-red-600 hover:bg-red-50"
    };
    return `
    <button class="p-1.5 rounded transition-colors ${variants[variant]}" ${title ? `title="${title}"` : ""} ${onClick ? `onclick="${onClick}"` : ""}>
      <i class="fas fa-${icon} text-sm"></i>
    </button>
  `;
  }
  function FileItem(file) {
    const typeStyles = {
      pdf: { bg: "bg-red-100", icon: "fa-file-pdf", iconColor: "text-red-500" },
      image: { bg: "bg-blue-100", icon: "fa-image", iconColor: "text-blue-500" },
      doc: { bg: "bg-blue-100", icon: "fa-file-word", iconColor: "text-blue-500" }
    };
    const style = typeStyles[file.type] || typeStyles.pdf;
    return `
    <div class="file-item group p-3 rounded-lg cursor-pointer transition-all ${file.selected ? "bg-primary-50 border border-primary-200" : "hover:bg-gray-50 border border-transparent"}">
      <div class="flex items-start gap-3">
        <div class="flex-shrink-0 w-10 h-10 rounded-lg ${style.bg} flex items-center justify-center">
          <i class="fas ${style.icon} ${style.iconColor}"></i>
        </div>
        <div class="flex-1 min-w-0">
          <p class="text-sm font-medium text-gray-800 truncate">${file.name}</p>
          <p class="text-xs text-gray-500">${file.size} \u2022 ${file.date}</p>
        </div>
        <div class="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
          ${IconButton({ icon: "trash-alt", title: "Excluir", variant: "danger" })}
        </div>
      </div>
    </div>
  `;
  }
  function TableRow(record) {
    const estadoBadges = {
      Analisado: "success",
      Pendente: "warning",
      Validado: "info",
      "Em Revis\xE3o": "warning"
    };
    return `
    <tr class="hover:bg-gray-50 transition-colors">
      <td class="px-4 py-3">
        ${record.children?.length ? IconButton({ icon: "chevron-right", variant: "ghost" }) : ""}
      </td>
      <td class="px-4 py-3 font-medium text-primary-600">${record.matricula}</td>
      <td class="px-4 py-3 text-gray-600">${record.dataOperacao}</td>
      <td class="px-4 py-3 text-gray-600">${record.tipo}</td>
      <td class="px-4 py-3 text-gray-800">${record.proprietario}</td>
      <td class="px-4 py-3">${Badge(record.estado, estadoBadges[record.estado])}</td>
      <td class="px-4 py-3">
        <div class="flex items-center gap-2">
          ${ProgressBar(record.confianca, "sm")}
          <span class="text-sm font-medium">${record.confianca}%</span>
        </div>
      </td>
      <td class="px-4 py-3">
        <div class="flex items-center justify-center gap-1">
          ${IconButton({ icon: "eye", title: "Visualizar", variant: "primary" })}
          ${IconButton({ icon: "edit", title: "Editar", variant: "primary" })}
          ${IconButton({ icon: "trash-alt", title: "Excluir", variant: "danger" })}
        </div>
      </td>
    </tr>
  `;
  }
  function LogEntry(log) {
    const statusColors = {
      success: { dot: "bg-green-500", text: "text-gray-300" },
      info: { dot: "bg-blue-500", text: "text-gray-300" },
      warning: { dot: "bg-yellow-500", text: "text-yellow-400" },
      error: { dot: "bg-red-500", text: "text-red-400" }
    };
    const style = statusColors[log.status] || statusColors.info;
    return `
    <div class="log-entry flex items-start gap-3 py-1">
      <span class="text-gray-500 flex-shrink-0">[${log.time}]</span>
      <span class="w-2 h-2 rounded-full ${style.dot} mt-1.5 flex-shrink-0"></span>
      <span class="${style.text}">${log.message}</span>
    </div>
  `;
  }
  function DetailCard({
    label,
    value,
    icon,
    badge = false,
    progress = null
  }) {
    let valueHtml = `<p class="text-sm font-medium text-gray-800 mt-1">${value}</p>`;
    if (badge) {
      valueHtml = `<span class="inline-block mt-1">${Badge(value, "success")}</span>`;
    } else if (progress !== null) {
      valueHtml = `
      <div class="mt-2 flex items-center gap-2">
        ${ProgressBar(progress)}
        <span class="text-sm font-semibold text-green-600">${value}</span>
      </div>
    `;
    }
    return `
    <div class="detail-card bg-gray-50 rounded-lg p-4 shadow-sm border border-gray-100 hover:shadow-md transition-shadow">
      <div class="flex items-start gap-3">
        <div class="w-8 h-8 rounded-lg bg-primary-100 flex items-center justify-center flex-shrink-0">
          <i class="fas fa-${icon} text-primary-600 text-sm"></i>
        </div>
        <div class="flex-1">
          <p class="text-xs text-gray-500 uppercase tracking-wider">${label}</p>
          ${valueHtml}
        </div>
      </div>
    </div>
  `;
  }
  function Modal({
    id,
    title,
    content,
    footer = "",
    size = "md"
  }) {
    const sizes = {
      sm: "max-w-md",
      md: "max-w-lg",
      lg: "max-w-2xl",
      xl: "max-w-4xl"
    };
    return `
    <div id="${id}" class="fixed inset-0 z-50 hidden">
      <div class="absolute inset-0 bg-black/50 backdrop-blur-sm"></div>
      <div class="absolute inset-0 flex items-center justify-center p-4">
        <div class="bg-white rounded-xl shadow-2xl ${sizes[size]} w-full max-h-[90vh] overflow-hidden">
          <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100">
            <h2 class="text-lg font-semibold text-gray-800">${title}</h2>
            <button onclick="closeModal('${id}')" class="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
              <i class="fas fa-times"></i>
            </button>
          </div>
          <div class="px-6 py-4 overflow-y-auto">
            ${content}
          </div>
          ${footer ? `
            <div class="px-6 py-4 border-t border-gray-100 flex justify-end gap-2">
              ${footer}
            </div>
          ` : ""}
        </div>
      </div>
    </div>
  `;
  }
  function openModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
      modal.classList.remove("hidden");
      modal.classList.add("fade-in");
    }
  }
  function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
      modal.classList.add("hidden");
    }
  }
  function showToast(message, type = "info") {
    const types = {
      success: { bg: "bg-green-500", icon: "check-circle" },
      error: { bg: "bg-red-500", icon: "times-circle" },
      warning: { bg: "bg-yellow-500", icon: "exclamation-triangle" },
      info: { bg: "bg-blue-500", icon: "info-circle" }
    };
    const style = types[type] || types.info;
    const toast = document.createElement("div");
    toast.className = `fixed bottom-24 right-4 ${style.bg} text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-3 z-50 fade-in`;
    toast.innerHTML = `
    <i class="fas fa-${style.icon}"></i>
    <span>${message}</span>
  `;
    document.body.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(10px)";
      toast.style.transition = "all 0.3s ease";
      setTimeout(() => toast.remove(), 300);
    }, 3e3);
  }
  function formatDateLocal(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString("pt-BR");
  }
  function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    return (bytes / (1024 * 1024 * 1024)).toFixed(1) + " GB";
  }
  function debounce(func, wait) {
    let timeout;
    return (...args) => {
      clearTimeout(timeout);
      timeout = setTimeout(() => func(...args), wait);
    };
  }
  window.Badge = Badge;
  window.Button = Button;
  window.Card = Card;
  window.ProgressBar = ProgressBar;
  window.IconButton = IconButton;
  window.FileItem = FileItem;
  window.TableRow = TableRow;
  window.LogEntry = LogEntry;
  window.DetailCard = DetailCard;
  window.Modal = Modal;
  window.openModal = openModal;
  window.closeModal = closeModal;
  window.showToast = showToast;
  window.formatDateLocal = formatDateLocal;
  window.formatFileSize = formatFileSize;
  window.debounce = debounce;
})();
//# sourceMappingURL=components.js.map
