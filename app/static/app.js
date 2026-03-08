document.addEventListener('DOMContentLoaded', () => {
    const fetchBtn = document.getElementById('fetchEmailsBtn');
    const resetDbBtn = document.getElementById('resetDbBtn');
    const tableBody = document.getElementById('tableBody');
    const rowTemplate = document.getElementById('rowTemplate');
    const detailsModal = document.getElementById('detailsModal');
    const modalContent = document.getElementById('modalContent');
    const closeModal = document.getElementById('closeModal');
    const showIgnoredToggle = document.getElementById('showIgnoredToggle');
    const downloadLogsBtn = document.getElementById('downloadLogsBtn');

    // Tabs
    const dashboardTab = document.querySelector('nav a:nth-child(1)');
    const settingsTab = document.querySelector('nav a:nth-child(2)');
    const dashboardView = document.getElementById('dashboardView');
    const settingsView = document.getElementById('settingsView');
    const headerActions = document.querySelector('.header-actions');

    dashboardTab.addEventListener('click', (e) => {
        e.preventDefault();
        dashboardTab.classList.add('active');
        settingsTab.classList.remove('active');
        dashboardView.style.display = 'block';
        settingsView.style.display = 'none';
        headerActions.style.display = 'flex';
    });

    settingsTab.addEventListener('click', (e) => {
        e.preventDefault();
        settingsTab.classList.add('active');
        dashboardTab.classList.remove('active');
        settingsView.style.display = 'block';
        dashboardView.style.display = 'none';
        headerActions.style.display = 'none'; // hide fetch/reset buttons
    });

    downloadLogsBtn.addEventListener('click', () => {
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = '/api/logs';
        a.download = 'light_invoice_app.log';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    });

    const submitFeedbackBtn = document.getElementById('submitFeedbackBtn');
    const feedbackText = document.getElementById('feedbackText');
    const feedbackStatus = document.getElementById('feedbackStatus');

    submitFeedbackBtn.addEventListener('click', async () => {
        const message = feedbackText.value.trim();
        if (!message) return;

        submitFeedbackBtn.disabled = true;
        try {
            const res = await fetch('/api/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message })
            });
            if (res.ok) {
                feedbackText.value = '';
                feedbackStatus.style.display = 'inline-block';
                setTimeout(() => { feedbackStatus.style.display = 'none'; }, 3000);
            }
        } catch (e) {
            console.error('Feedback error:', e);
        } finally {
            submitFeedbackBtn.disabled = false;
        }
    });

    showIgnoredToggle.addEventListener('change', () => {
        renderTable(currentRequests);
    });

    const saveConfigBtn = document.getElementById('saveConfigBtn');
    const configSaveStatus = document.getElementById('configSaveStatus');

    async function loadConfig() {
        try {
            const res = await fetch('/api/config');
            const cfg = await res.json();
            document.getElementById('cfgImapServer').value = cfg.imap_server;
            document.getElementById('cfgImapPort').value = cfg.imap_port;
            document.getElementById('cfgImapUser').value = cfg.imap_user;
            document.getElementById('cfgImapPass').value = cfg.imap_pass;
            document.getElementById('cfgSearchUser').value = cfg.yandex_search_user;
            document.getElementById('cfgSearchKey').value = cfg.yandex_search_key;
        } catch (e) {
            console.error('Failed to load config:', e);
        }
    }

    saveConfigBtn.addEventListener('click', async () => {
        const payload = {
            imap_server: document.getElementById('cfgImapServer').value,
            imap_port: document.getElementById('cfgImapPort').value,
            imap_user: document.getElementById('cfgImapUser').value,
            imap_pass: document.getElementById('cfgImapPass').value,
            yandex_search_user: document.getElementById('cfgSearchUser').value,
            yandex_search_key: document.getElementById('cfgSearchKey').value
        };

        saveConfigBtn.disabled = true;
        try {
            const res = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (res.ok) {
                configSaveStatus.textContent = data.message;
                configSaveStatus.style.display = 'inline-block';
                configSaveStatus.style.color = '#2ecc71';
            } else {
                configSaveStatus.textContent = "Ошибка сохранения";
                configSaveStatus.style.display = 'inline-block';
            }
        } catch (e) {
            console.error(e);
        } finally {
            saveConfigBtn.disabled = false;
        }
    });

    // Global store for requests to access them from click handlers
    let currentRequests = [];

    // Status translation and styling
    const statusMap = {
        'new': { text: 'Новая', class: 'new' },
        'processing': { text: 'В обработке', class: 'processing' },
        'ready': { text: 'Готово', class: 'ready' },
        'error': { text: 'Ошибка', class: 'error' },
        'ignored': { text: 'Игнорируется', class: 'ignored' }
    };

    function formatDate(dateString) {
        const d = new Date(dateString);
        return d.toLocaleDateString('ru-RU', {
            day: '2-digit', month: 'short', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
    }

    async function loadRequests() {
        try {
            const res = await fetch('/api/requests');
            currentRequests = await res.json();
            renderTable(currentRequests);
        } catch (e) {
            console.error('Failed to load:', e);
            tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:red">Ошибка загрузки данных</td></tr>`;
        }
    }

    function renderTable(requests) {
        tableBody.innerHTML = '';

        let filteredRequests = requests;
        if (!showIgnoredToggle.checked) {
            filteredRequests = requests.filter(r => r.status !== 'ignored');
        }

        if (filteredRequests.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 40px; color: var(--text-sub)">Нет текущих заявок</td></tr>`;
            return;
        }

        filteredRequests.forEach(req => {
            const clone = rowTemplate.content.cloneNode(true);

            // Basic text fields
            clone.querySelector('.sender').textContent = req.sender;
            clone.querySelector('.subject').textContent = req.subject;
            clone.querySelector('.date').textContent = formatDate(req.received_at);

            // Status Badge
            const badgeMeta = statusMap[req.status] || { text: req.status, class: 'new' };
            const badge = clone.querySelector('.badge');
            badge.textContent = badgeMeta.text;
            badge.classList.add(badgeMeta.class);

            // Items List
            const ul = clone.querySelector('.items-list');
            if (req.items && req.items.length > 0) {
                req.items.forEach(item => {
                    const li = document.createElement('li');

                    const nameDiv = document.createElement('div');
                    nameDiv.className = 'item-name';
                    nameDiv.textContent = item.found_name || item.original_name;

                    const metaDiv = document.createElement('div');
                    metaDiv.className = 'item-meta';

                    const qtySpan = document.createElement('span');
                    qtySpan.textContent = `${item.quantity || 1} ${item.unit}`;

                    const priceSpan = document.createElement('span');
                    if (item.price) {
                        priceSpan.textContent = `₽${item.price.toFixed(2)}`;
                    } else {
                        priceSpan.textContent = "—";
                    }

                    metaDiv.appendChild(qtySpan);
                    metaDiv.appendChild(priceSpan);

                    li.appendChild(nameDiv);
                    li.appendChild(metaDiv);

                    // Source Link
                    if (item.source_url) {
                        const link = document.createElement('a');
                        link.href = item.source_url;
                        link.target = "_blank";
                        link.className = "source-link";
                        link.textContent = item.supplier_name || "Источник";
                        link.style.display = "block";
                        link.style.marginTop = "4px";
                        li.appendChild(link);
                    }

                    ul.appendChild(li);
                });
            } else if (req.status === 'new') {
                const li = document.createElement('li');
                li.style.color = "var(--text-sub)";
                li.innerHTML = `<div class="spinner" style="display:inline-block; margin-right:5px; height:12px; width:12px;"></div> Распознавание заказа...`;
                ul.appendChild(li);
            } else {
                const li = document.createElement('li');
                li.style.color = "var(--text-sub)";
                li.textContent = "Нет извлеченных товаров";
                ul.appendChild(li);
            }

            // Invoice Link
            const invoiceCell = clone.querySelector('.invoice-link');
            if (req.status === 'ready' && req.invoice_path) {
                const a = document.createElement('a');
                // Extract filename from path to use in url
                const filename = req.invoice_path.split('/').pop();
                a.href = `/invoices/${filename}`;
                a.target = "_blank";
                a.className = "pdf-link";
                a.innerHTML = `📄 Скачать`;
                invoiceCell.appendChild(a);
            } else if (req.status === 'processing') {
                invoiceCell.innerHTML = `<span style="color: var(--text-sub); font-size: 0.85rem">Генерация...</span>`;
            } else {
                invoiceCell.textContent = "—";
            }

            // View Details Button
            const viewBtn = clone.querySelector('.view-details');
            viewBtn.addEventListener('click', () => showDetails(req));

            tableBody.appendChild(clone);
        });
    }

    function showDetails(req) {
        modalContent.innerHTML = `
            <div style="margin-bottom: 20px;">
                <div style="color: var(--text-sub); font-size: 0.85rem; margin-bottom: 4px;">Отправитель</div>
                <div style="font-weight: 500">${req.sender}</div>
            </div>
            <div style="margin-bottom: 20px;">
                <div style="color: var(--text-sub); font-size: 0.85rem; margin-bottom: 4px;">Тема</div>
                <div style="font-weight: 500">${req.subject}</div>
            </div>
            <div style="margin-bottom: 20px;">
                <div style="color: var(--text-sub); font-size: 0.85rem; margin-bottom: 4px;">Текст письма</div>
                <pre>${req.body_text || "Текст отсутствует"}</pre>
            </div>
            <div>
                <div style="color: var(--text-sub); font-size: 0.85rem; margin-bottom: 8px;">Извлеченные позиции:</div>
                <ul class="items-list">
                    ${req.items.map(item => `
                        <li>
                            <div class="item-name">${item.found_name || item.original_name}</div>
                            <div class="item-meta">
                                <span>${item.quantity} ${item.unit}</span>
                                <span>${item.price ? `₽${item.price.toFixed(2)}` : '—'}</span>
                            </div>
                        </li>
                    `).join('') || '<li style="color: var(--text-sub)">Нет позиций</li>'}
                </ul>
            </div>
        `;
        detailsModal.classList.add('show');
    }

    closeModal.addEventListener('click', () => {
        detailsModal.classList.remove('show');
    });

    detailsModal.addEventListener('click', (e) => {
        if (e.target === detailsModal) {
            detailsModal.classList.remove('show');
        }
    });

    fetchBtn.addEventListener('click', async () => {
        const originalContent = fetchBtn.innerHTML;
        fetchBtn.innerHTML = `<div class="spinner"></div> Загрузка...`;
        fetchBtn.disabled = true;

        try {
            await fetch('/api/fetch_emails', { method: 'POST' });
            // Small delay to let background task register
            setTimeout(loadRequests, 500);
        } catch (e) {
            console.error(e);
            alert("Ошибка при получении писем");
        } finally {
            fetchBtn.innerHTML = originalContent;
            fetchBtn.disabled = false;
        }
    });

    resetDbBtn.addEventListener('click', async () => {
        if (!confirm("Вы уверены, что хотите удалить все заявки и очистить базу данных? Это действие нельзя отменить.")) {
            return;
        }

        const originalContent = resetDbBtn.innerHTML;
        resetDbBtn.innerHTML = `<div class="spinner"></div> Удаление...`;
        resetDbBtn.disabled = true;

        try {
            await fetch('/api/reset', { method: 'POST' });
            await loadRequests();
        } catch (e) {
            console.error(e);
            alert("Ошибка при очистке БД");
        } finally {
            resetDbBtn.innerHTML = originalContent;
            resetDbBtn.disabled = false;
        }
    });

    // Auto-refresh every 5 seconds if there are items processing
    setInterval(() => {
        const processingBadges = document.querySelectorAll('.badge.processing');
        if (processingBadges.length > 0) {
            loadRequests();
        }
    }, 5000);

    // Initial load
    loadRequests();
    loadConfig();
});
