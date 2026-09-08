/**
 * AppDialog & AppToast - Universal Custom Popups, Modals & Toast Notifications
 * Replaces native browser alert(), confirm(), and prompt() with modern dark-themed dialogs.
 */

(function () {
    // -------------------------------------------------------------
    // 1. TOAST NOTIFICATION ENGINE
    // -------------------------------------------------------------
    const AppToast = {
        container: null,

        _ensureContainer() {
            if (!this.container || !document.body.contains(this.container)) {
                this.container = document.createElement('div');
                this.container.id = 'app-toast-container';
                this.container.className = 'fixed top-5 right-5 z-[9999] flex flex-col gap-2.5 max-w-sm w-full pointer-events-none px-4 sm:px-0';
                document.body.appendChild(this.container);
            }
            return this.container;
        },

        show(message, type = 'info', duration = 3500) {
            const container = this._ensureContainer();

            const toast = document.createElement('div');
            toast.className = 'pointer-events-auto transform transition-all duration-300 ease-out translate-y-2 opacity-0 flex items-start gap-3 p-3.5 rounded-xl border shadow-2xl backdrop-blur-md text-xs font-medium';

            let typeStyles = {
                success: {
                    border: 'border-emerald-500/30',
                    bg: 'bg-zinc-900/95 text-zinc-100',
                    iconBg: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
                    iconSvg: `<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`
                },
                error: {
                    border: 'border-rose-500/30',
                    bg: 'bg-zinc-900/95 text-zinc-100',
                    iconBg: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
                    iconSvg: `<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`
                },
                warning: {
                    border: 'border-amber-500/30',
                    bg: 'bg-zinc-900/95 text-zinc-100',
                    iconBg: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
                    iconSvg: `<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`
                },
                info: {
                    border: 'border-sky-500/30',
                    bg: 'bg-zinc-900/95 text-zinc-100',
                    iconBg: 'bg-sky-500/10 text-sky-400 border-sky-500/20',
                    iconSvg: `<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`
                }
            };

            const style = typeStyles[type] || typeStyles.info;
            toast.className += ` ${style.border} ${style.bg}`;

            toast.innerHTML = `
                <div class="w-7 h-7 rounded-lg ${style.iconBg} border flex items-center justify-center shrink-0 mt-0.5">
                    ${style.iconSvg}
                </div>
                <div class="flex-1 pt-0.5 leading-snug">
                    ${message}
                </div>
                <button type="button" class="text-zinc-400 hover:text-zinc-200 p-1 rounded transition-colors -mr-1 -mt-1" title="Dismiss">
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                </button>
            `;

            const closeBtn = toast.querySelector('button');
            const removeToast = () => {
                toast.classList.add('opacity-0', '-translate-y-2');
                setTimeout(() => toast.remove(), 300);
            };

            closeBtn.addEventListener('click', removeToast);
            container.appendChild(toast);

            // Trigger reflow & animate in
            requestAnimationFrame(() => {
                toast.classList.remove('opacity-0', 'translate-y-2');
                toast.classList.add('opacity-100', 'translate-y-0');
            });

            if (duration > 0) {
                setTimeout(removeToast, duration);
            }

            return toast;
        },

        success(msg, dur) { return this.show(msg, 'success', dur); },
        error(msg, dur) { return this.show(msg, 'error', dur || 4500); },
        warning(msg, dur) { return this.show(msg, 'warning', dur); },
        info(msg, dur) { return this.show(msg, 'info', dur); }
    };


    // -------------------------------------------------------------
    // 2. DIALOG & MODAL SYSTEM (CONFIRM, PROMPT, ALERT)
    // -------------------------------------------------------------
    const AppDialog = {
        _activeModal: null,

        confirm({
            title = 'Are you sure?',
            message = 'This action cannot be undone.',
            confirmText = 'Confirm',
            cancelText = 'Cancel',
            type = 'danger' // 'danger' | 'warning' | 'info'
        } = {}) {
            return new Promise((resolve) => {
                const overlay = document.createElement('div');
                overlay.className = 'fixed inset-0 z-[9999] bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-150';

                let iconSvg = '';
                let iconBg = '';
                let confirmBtnClass = '';

                if (type === 'danger') {
                    iconBg = 'bg-rose-500/10 border-rose-500/20 text-rose-400';
                    iconSvg = `<svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>`;
                    confirmBtnClass = 'bg-rose-600 hover:bg-rose-500 text-white shadow-lg shadow-rose-950/50';
                } else if (type === 'warning') {
                    iconBg = 'bg-amber-500/10 border-amber-500/20 text-amber-400';
                    iconSvg = `<svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`;
                    confirmBtnClass = 'bg-amber-600 hover:bg-amber-500 text-white shadow-lg shadow-amber-950/50';
                } else {
                    iconBg = 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400';
                    iconSvg = `<svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`;
                    confirmBtnClass = 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-950/50';
                }

                overlay.innerHTML = `
                    <div class="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4 transform transition-all duration-200 scale-95 opacity-0">
                        <div class="flex items-start gap-4">
                            <div class="w-12 h-12 rounded-xl ${iconBg} border flex items-center justify-center shrink-0">
                                ${iconSvg}
                            </div>
                            <div class="space-y-1 flex-1">
                                <h3 class="text-sm font-bold text-white tracking-tight">${title}</h3>
                                <p class="text-xs text-zinc-400 leading-relaxed">${message}</p>
                            </div>
                        </div>

                        <div class="flex items-center justify-end gap-2.5 pt-2 border-t border-zinc-800/80">
                            ${cancelText ? `
                            <button type="button" class="btn-cancel px-4 py-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-semibold transition-colors border border-zinc-700/60">
                                ${cancelText}
                            </button>` : ''}
                            <button type="button" class="btn-confirm px-4 py-2 rounded-xl text-xs font-bold transition-colors ${confirmBtnClass}">
                                ${confirmText}
                            </button>
                        </div>
                    </div>
                `;

                document.body.appendChild(overlay);
                const modalBox = overlay.firstElementChild;

                requestAnimationFrame(() => {
                    modalBox.classList.remove('scale-95', 'opacity-0');
                    modalBox.classList.add('scale-100', 'opacity-100');
                });

                const confirmBtn = overlay.querySelector('.btn-confirm');
                const cancelBtn = overlay.querySelector('.btn-cancel');

                confirmBtn?.focus();

                const cleanup = (result) => {
                    modalBox.classList.add('scale-95', 'opacity-0');
                    setTimeout(() => {
                        overlay.remove();
                        resolve(result);
                    }, 150);
                };

                confirmBtn?.addEventListener('click', () => cleanup(true));
                cancelBtn?.addEventListener('click', () => cleanup(false));

                overlay.addEventListener('click', (e) => {
                    if (e.target === overlay) cleanup(false);
                });

                const onKeyDown = (e) => {
                    if (e.key === 'Escape') {
                        document.removeEventListener('keydown', onKeyDown);
                        cleanup(false);
                    } else if (e.key === 'Enter') {
                        document.removeEventListener('keydown', onKeyDown);
                        cleanup(true);
                    }
                };
                document.addEventListener('keydown', onKeyDown);
            });
        },

        confirmDelete(itemName = 'this item', onConfirm) {
            return this.confirm({
                title: `Delete ${itemName}?`,
                message: `Are you sure you want to permanently delete ${itemName}? All associated output files and metadata will be permanently removed.`,
                confirmText: 'Delete Permanently',
                cancelText: 'Cancel',
                type: 'danger'
            }).then(confirmed => {
                if (confirmed && typeof onConfirm === 'function') {
                    onConfirm();
                }
                return confirmed;
            });
        },

        alert({
            title = 'Notice',
            message = '',
            confirmText = 'OK',
            type = 'info'
        } = {}) {
            return this.confirm({
                title,
                message,
                confirmText,
                cancelText: '',
                type
            }).then(() => {});
        },

        prompt({
            title = 'Input Required',
            message = '',
            placeholder = '',
            defaultValue = '',
            confirmText = 'Save',
            cancelText = 'Cancel'
        } = {}) {
            return new Promise((resolve) => {
                const overlay = document.createElement('div');
                overlay.className = 'fixed inset-0 z-[9999] bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-150';

                overlay.innerHTML = `
                    <div class="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4 transform transition-all duration-200 scale-95 opacity-0">
                        <div class="space-y-1.5">
                            <h3 class="text-sm font-bold text-white tracking-tight">${title}</h3>
                            ${message ? `<p class="text-xs text-zinc-400 leading-relaxed">${message}</p>` : ''}
                        </div>

                        <div>
                            <input type="text" class="prompt-input w-full px-3.5 py-2.5 bg-zinc-950 border border-zinc-800 rounded-xl text-xs text-white placeholder-zinc-500 focus:outline-none focus:border-zinc-600 font-sans" placeholder="${placeholder}" value="${defaultValue.replace(/"/g, '&quot;')}">
                        </div>

                        <div class="flex items-center justify-end gap-2.5 pt-2 border-t border-zinc-800/80">
                            <button type="button" class="btn-cancel px-4 py-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-semibold transition-colors border border-zinc-700/60">
                                ${cancelText}
                            </button>
                            <button type="button" class="btn-confirm px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition-colors shadow-lg shadow-emerald-950/50">
                                ${confirmText}
                            </button>
                        </div>
                    </div>
                `;

                document.body.appendChild(overlay);
                const modalBox = overlay.firstElementChild;
                const input = overlay.querySelector('.prompt-input');
                const confirmBtn = overlay.querySelector('.btn-confirm');
                const cancelBtn = overlay.querySelector('.btn-cancel');

                requestAnimationFrame(() => {
                    modalBox.classList.remove('scale-95', 'opacity-0');
                    modalBox.classList.add('scale-100', 'opacity-100');
                    input?.focus();
                    input?.select();
                });

                const cleanup = (val) => {
                    modalBox.classList.add('scale-95', 'opacity-0');
                    setTimeout(() => {
                        overlay.remove();
                        resolve(val);
                    }, 150);
                };

                confirmBtn?.addEventListener('click', () => cleanup(input.value));
                cancelBtn?.addEventListener('click', () => cleanup(null));

                input?.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') cleanup(input.value);
                    else if (e.key === 'Escape') cleanup(null);
                });

                overlay.addEventListener('click', (e) => {
                    if (e.target === overlay) cleanup(null);
                });
            });
        }
    };

    // -------------------------------------------------------------
    // 3. GLOBAL DECLARATIVE FORM & DELETE INTERCEPTOR
    // -------------------------------------------------------------
    document.addEventListener('DOMContentLoaded', () => {
        document.body.addEventListener('submit', async (e) => {
            const form = e.target;
            const confirmMsg = form.getAttribute('data-confirm') || form.getAttribute('data-delete-confirm');
            if (confirmMsg && !form.dataset.confirmed) {
                e.preventDefault();
                const isDelete = form.hasAttribute('data-delete-confirm') || confirmMsg.toLowerCase().includes('delete');
                const ok = await AppDialog.confirm({
                    title: isDelete ? 'Confirm Deletion' : 'Confirm Action',
                    message: confirmMsg,
                    confirmText: isDelete ? 'Yes, Delete' : 'Confirm',
                    cancelText: 'Cancel',
                    type: isDelete ? 'danger' : 'info'
                });
                if (ok) {
                    form.dataset.confirmed = 'true';
                    form.submit();
                }
            }
        });
    });

    // Expose globally to window
    window.AppToast = AppToast;
    window.AppDialog = AppDialog;
})();
