// 題目篩選與出卷邏輯 v3.0
(function() {
    let allQuestions = [];
    let selectedQuestions = []; // 考卷內的題目
    let currentTimestamp = "";
    
    const ASSET_VERSION = "20260713-rt4";
    const SOURCE_COLUMN_WIDTH = 1000;

    function normalizeStackedPreviewImage(image) {
        const applyScale = () => {
            const widthPercent = Math.min(100, image.naturalWidth / SOURCE_COLUMN_WIDTH * 100);
            image.style.width = `${widthPercent}%`;
        };
        if (image.complete && image.naturalWidth) {
            applyScale();
        } else {
            image.addEventListener('load', applyScale, { once: true });
        }
    }

    function versionAssetPath(path) {
        if (!path) return path;
        const separator = path.includes('?') ? '&' : '?';
        return `${path}${separator}v=${ASSET_VERSION}`;
    }

    const STANDARD_TYPES = [
        "注音_書寫",
        "字詞_書寫",
        "注音_拼音",
        "字詞_認識",
        "字詞_應用",
        "句段_閱讀",
        "篇章_閱讀"
    ];
    
    const TYPE_CLASSES = {
        "注音_書寫": "row-bopomofo-write",
        "字詞_書寫": "row-word-write",
        "注音_拼音": "row-bopomofo-match",
        "字詞_認識": "row-word-recog",
        "字詞_應用": "row-word-apply",
        "句段_閱讀": "row-sentence-read",
        "篇章_閱讀": "row-passage-read"
    };
    
    // 民國年轉西元年標籤
    function formatYearLabel(rocYear) {
        const adYear = parseInt(rocYear) + 1911;
        return `${adYear} 年份`;
    }

    function getFormattedYearsString() {
        const selectedYears = getSelectedYears();
        if (selectedYears.length === 0) return "";
        
        const westernYears = selectedYears.map(y => parseInt(y) + 1911).sort((a, b) => a - b);
        
        const groups = [];
        let currentGroup = [westernYears[0]];
        for (let i = 1; i < westernYears.length; i++) {
            const y = westernYears[i];
            if (y === currentGroup[currentGroup.length - 1] + 1) {
                currentGroup.push(y);
            } else {
                groups.push(currentGroup);
                currentGroup = [y];
            }
        }
        groups.push(currentGroup);
        
        const parts = [];
        groups.forEach(g => {
            if (g.length === 1) {
                parts.push(String(g[0]));
            } else {
                parts.push(`${g[0]}-${g[g.length - 1]}`);
            }
        });
        
        return parts.join(',');
    }

    function updateDefaultTitle() {
        const paperTitleInput = document.getElementById('paper-title');
        if (!paperTitleInput) return;
        
        const yearsStr = getFormattedYearsString();
    const yearPart = yearsStr ? `(${yearsStr})` : "";
    const subject = document.getElementById('filter-subject')?.value || "";
    const subjectPart = subject ? `${subject}科` : "";
    paperTitleInput.value = `歷屆篩選測驗${subjectPart}${yearPart}`;
    }
    
    // 初始化
    document.addEventListener('DOMContentLoaded', () => {
        const paperTitleInput = document.getElementById('paper-title');
        if (paperTitleInput) {
            const now = new Date();
            const MM = String(now.getMonth() + 1).padStart(2, '0');
            const DD = String(now.getDate()).padStart(2, '0');
            const HH = String(now.getHours()).padStart(2, '0');
            const mm = String(now.getMinutes()).padStart(2, '0');
            currentTimestamp = `${MM}${DD}${HH}${mm}`;
            paperTitleInput.value = `歷屆篩選測驗`;
        }
        
        setupGeneratorEvents();
        window.loadQuestionsFromDb = loadQuestions;
        loadQuestions();
    });
    
    // 1. 從後端載入所有題目
    async function loadQuestions() {
        try {
            const res = await fetch('./data/questions.json', { cache: 'no-cache' });
            const questions = await res.json();
            allQuestions = questions.map(question => ({
                ...question,
                imagePath: versionAssetPath(question.imagePath),
                imagePaths: (question.imagePaths || []).map(versionAssetPath)
            }));
            
            // 初始化複選核取方塊
            initFilterOptions();
            initYearCheckboxes();
            initTypeRows();
            
            // 執行篩選渲染
            filterAndRender();
        } catch (err) {
            console.error('無法取得題庫資料:', err);
            showToast('無法連接資料庫！', 'error');
        }
    }
    
    // 2. 初始化年份複選框 (預設選中 112, 113, 114)
    function initFilterOptions() {
        const subjectSelect = document.getElementById('filter-subject');
        const gradeSelect = document.getElementById('filter-grade');
        const previousSubject = subjectSelect?.value;
        const previousGrade = gradeSelect?.value;
        const subjects = [...new Set(allQuestions.map(q => q.subject).filter(Boolean))].sort();
        const gradeOrder = ['\u4e00\u5e74\u7d1a', '\u4e8c\u5e74\u7d1a', '\u4e09\u5e74\u7d1a', '\u56db\u5e74\u7d1a', '\u4e94\u5e74\u7d1a', '\u516d\u5e74\u7d1a'];
        const grades = [...new Set(allQuestions.map(q => q.grade).filter(Boolean))]
            .sort((a, b) => gradeOrder.indexOf(a) - gradeOrder.indexOf(b));
        const fill = (select, values, preferred, placeholder) => {
            if (!select) return;
            select.innerHTML = '';
            const emptyOption = document.createElement('option');
            emptyOption.value = '';
            emptyOption.textContent = placeholder;
            select.appendChild(emptyOption);
            values.forEach(value => {
                const option = document.createElement('option');
                option.value = value;
                option.textContent = value;
                select.appendChild(option);
            });
            select.value = values.includes(preferred) ? preferred : '';
        };
        fill(subjectSelect, subjects, previousSubject, '選擇科目');
        fill(gradeSelect, grades, previousGrade, '選擇年級');
        [...new Set(allQuestions.map(q => q.type).filter(Boolean))].forEach(type => {
            if (!STANDARD_TYPES.includes(type)) STANDARD_TYPES.push(type);
        });
    }

    function initYearCheckboxes() {
        const container = document.getElementById('year-checkboxes-container');
        container.innerHTML = '';
        
        // 抓出資料庫中的所有年份並排序 (由小到大)
        const years = Array.from(new Set(allQuestions.map(q => q.year))).sort((a, b) => parseInt(a) - parseInt(b));
        
        if (years.length === 0) {
            container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.88rem;">無年份資料</div>';
            return;
        }
        
        years.forEach(year => {
            const label = document.createElement('label');
            label.className = 'year-checkbox-item';
            
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.value = year;
            checkbox.className = 'year-filter-cb';
            
            // 年份預設全部不選，讓老師先明確指定題庫範圍。
            checkbox.checked = false;
            
            checkbox.addEventListener('change', () => {
                updateLabelsHighlight();
                updateDefaultTitle();
                filterAndRender();
            });
            
            label.appendChild(checkbox);
            label.appendChild(document.createTextNode(` ${formatYearLabel(year)}`));
            container.appendChild(label);
        });
        
        updateLabelsHighlight();
        updateDefaultTitle();
    }
    
    // 3. 初始化七大題型列 (包括抽幾題輸入框、全選按鈕)
    function initTypeRows() {
        const container = document.getElementById('type-rows-container');
        container.innerHTML = '';
        
        STANDARD_TYPES.forEach(type => {
            const rowClass = TYPE_CLASSES[type] || 'row-word-apply';
            const row = document.createElement('div');
            row.className = `type-row ${rowClass}`;
            row.id = `type-row-${type}`;
            
            // 左側部分
            const leftDiv = document.createElement('div');
            leftDiv.className = 'type-row-left';
            
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.value = type;
            checkbox.checked = false; // 預設不勾選，交由老師選擇
            checkbox.className = 'type-row-cb';
            checkbox.id = `cb-${type}`;
            
            checkbox.addEventListener('change', () => {
                updateLabelsHighlight();
                filterAndRender();
            });
            
            const nameLabel = document.createElement('label');
            nameLabel.htmlFor = `cb-${type}`;
            nameLabel.className = 'type-row-name';
            nameLabel.textContent = type;
            
            const badge = document.createElement('span');
            badge.className = 'type-row-badge';
            badge.id = `badge-${type}`;
            
            leftDiv.appendChild(checkbox);
            leftDiv.appendChild(nameLabel);
            leftDiv.appendChild(badge);
            
            // 中間部分：輸入抽幾題
            const centerDiv = document.createElement('div');
            centerDiv.className = 'type-row-center';
            
            const drawInput = document.createElement('input');
            drawInput.type = 'number';
            drawInput.className = 'draw-input';
            drawInput.placeholder = '抽幾題';
            drawInput.min = '0';
            drawInput.id = `draw-input-${type}`;
            
            // 監聽輸入框數值變化：隨機抽出題目
            drawInput.addEventListener('input', () => {
                handleRandomDraw(type, parseInt(drawInput.value) || 0);
            });
            
            centerDiv.appendChild(drawInput);
            
            // 右側部分：一鍵全選按鈕
            const rightDiv = document.createElement('div');
            rightDiv.className = 'type-row-right';
            
            const btnAll = document.createElement('button');
            btnAll.type = 'button';
            btnAll.className = 'secondary-btn small-btn';
            btnAll.textContent = '全選';
            
            btnAll.addEventListener('click', () => {
                selectAllOfType(type);
            });
            
            rightDiv.appendChild(btnAll);
            
            // 組合
            row.appendChild(leftDiv);
            row.appendChild(centerDiv);
            row.appendChild(rightDiv);
            
            container.appendChild(row);
        });
        
        updateLabelsHighlight();
    }
    
    // 更新高亮與統計數量
    function updateLabelsHighlight() {
        // 更新年份高亮樣式
        document.querySelectorAll('.year-checkbox-item').forEach(label => {
            const cb = label.querySelector('input');
            if (cb && cb.checked) {
                label.classList.add('checked');
            } else {
                label.classList.remove('checked');
            }
        });
        
        // 取得當前勾選的年份
        const selectedYears = getSelectedYears();
        
        // 更新各題型的總計/可選統計
        STANDARD_TYPES.forEach(type => {
            const badge = document.getElementById(`badge-${type}`);
            const row = document.getElementById(`type-row-${type}`);
            const cb = document.getElementById(`cb-${type}`);
            
            if (row && cb) {
                if (cb.checked) {
                    row.classList.add('checked');
                } else {
                    row.classList.remove('checked');
                }
            }
            
            if (!badge) return;
            
            const gradeVal = document.getElementById('filter-grade') ? document.getElementById('filter-grade').value : "一年級";
            const subjectVal = document.getElementById('filter-subject') ? document.getElementById('filter-subject').value : "國語";
            
            // 可選：符合目前勾選年份、且符合當前年級與科目的題數
            const selectable = allQuestions.filter(q => {
                return q.type === type && 
                       q.grade === gradeVal &&
                       q.subject === subjectVal &&
                       selectedYears.includes(q.year);
            }).length;
            
            const selectedCount = selectedQuestions.filter(q => q.type === type && q.grade === gradeVal && q.subject === subjectVal).length;
            if (type === "篇章_閱讀") {
                badge.textContent = `已選 ${selectedCount} 組 / 可選 ${selectable} 組`;
            } else {
                badge.textContent = `已選 ${selectedCount} 題 / 可選 ${selectable} 題`;
            }
            
            // 同時更新輸入框的最大上限
            const drawInput = document.getElementById(`draw-input-${type}`);
            if (drawInput) {
                drawInput.max = selectable;
            }
        });
        
        // 更新已選題目數顯示
        document.getElementById('paper-q-count').textContent = selectedQuestions.length;
    }
    
    // 4. 隨機抽題邏輯
    function handleRandomDraw(type, count) {
        const selectedYears = getSelectedYears();
        const gradeVal = document.getElementById('filter-grade') ? document.getElementById('filter-grade').value : "一年級";
        const subjectVal = document.getElementById('filter-subject') ? document.getElementById('filter-subject').value : "國語";
        
        // 1. 獲取符合年份、科目、年級、屬於此題型的全部題庫
        const pool = allQuestions.filter(q => q.type === type && q.grade === gradeVal && q.subject === subjectVal && selectedYears.includes(q.year));
        
        // 限制抽題數量不超過庫存
        if (count > pool.length) {
            count = pool.length;
            const drawInput = document.getElementById(`draw-input-${type}`);
            if (drawInput) drawInput.value = count;
        }
        
        // 2. 先把考卷內該題型的題目全部清除
        selectedQuestions = selectedQuestions.filter(q => q.type !== type);
        
        if (count > 0) {
            // 3. 隨機洗牌池子
            const shuffledPool = shuffleArray([...pool]);
            // 4. 取前 N 個題目加入考卷
            const drawn = shuffledPool.slice(0, count);
            selectedQuestions = selectedQuestions.concat(drawn);
        }
        
        renderPaperList();
        updateLabelsHighlight();
    }
    
    // 5. 題型一鍵「全選」邏輯
    function selectAllOfType(type) {
        const selectedYears = getSelectedYears();
        const gradeVal = document.getElementById('filter-grade') ? document.getElementById('filter-grade').value : "一年級";
        const subjectVal = document.getElementById('filter-subject') ? document.getElementById('filter-subject').value : "國語";
        
        // 獲取符合年份、科目、年級、屬於此題型的全部題庫
        const pool = allQuestions.filter(q => q.type === type && q.grade === gradeVal && q.subject === subjectVal && selectedYears.includes(q.year));
        
        if (pool.length === 0) {
            showToast('此年份內沒有此題型的題目喔！', 'error');
            return;
        }
        
        // 把此題型的題目全部加入考卷 (避免重複)
        pool.forEach(q => {
            if (!selectedQuestions.some(item => item.id === q.id)) {
                selectedQuestions.push(q);
            }
        });
        
        // 更新輸入框數值為最大庫存
        const drawInput = document.getElementById(`draw-input-${type}`);
        if (drawInput) {
            drawInput.value = pool.length;
        }
        
        renderPaperList();
        updateLabelsHighlight();
        showToast(`已將 ${pool.length} 題「${type}」加入考卷`);
    }
    
    // 6. 輔助函式：獲取當前選取的年份與題型
    function getSelectedYears() {
        return Array.from(document.querySelectorAll('.year-filter-cb'))
                    .filter(cb => cb.checked)
                    .map(cb => cb.value);
    }
    
    // 7. 題庫篩選與顯示
    function getSelectedTypes() {
        return Array.from(document.querySelectorAll('.type-row-cb'))
                    .filter(cb => cb.checked)
                    .map(cb => cb.value);
    }
    
    function filterAndRender() {
        const selectedYears = getSelectedYears();
        const selectedTypes = getSelectedTypes();
        const gradeVal = document.getElementById('filter-grade') ? document.getElementById('filter-grade').value : "一年級";
        const subjectVal = document.getElementById('filter-subject') ? document.getElementById('filter-subject').value : "國語";
        
        const hasCompleteFilters = Boolean(gradeVal && subjectVal && selectedYears.length > 0);
        const filtered = hasCompleteFilters ? allQuestions.filter(q => {
            if (q.grade !== gradeVal) return false;
            if (q.subject !== subjectVal) return false;
            if (!selectedYears.includes(q.year)) return false;
            if (selectedTypes.length > 0 && !selectedTypes.includes(q.type)) return false;
            return true;
        }) : [];
        
        document.getElementById('stat-filtered-q').textContent = filtered.length;
        renderResultsGrid(filtered);
    }
    
    // 渲染題目搜尋結果網格
    function renderResultsGrid(questions) {
        const grid = document.getElementById('results-grid');
        
        if (questions.length === 0) {
            grid.innerHTML = '<div class="no-results">📭 沒有符合篩選條件的題目。</div>';
            return;
        }
        
        grid.innerHTML = '';
        
        questions.forEach(q => {
            const card = document.createElement('div');
            card.className = 'q-card';
            
            const hasMultiImages = q.imagePaths && q.imagePaths.length > 1;
            let imageBoxHtml = '';
            
            if (hasMultiImages) {
                imageBoxHtml = `<div class="q-card-image-box multi-images">`;
                q.imagePaths.forEach(path => {
                    imageBoxHtml += `<img src="${path}" alt="題目" class="preview-img-stacked">`;
                });
                imageBoxHtml += `</div>`;
            } else {
                const firstImgPath = q.imagePaths && q.imagePaths.length > 0 ? q.imagePaths[0] : (q.imagePath || '');
                imageBoxHtml = `
                    <div class="q-card-image-box">
                        <img src="${firstImgPath}" alt="題目預覽">
                    </div>
                `;
            }
            
            let tagsHtml = `
                <span class="badge year-badge">${formatYearLabel(q.year)}</span>
                <span class="badge primary-badge">${q.subject}</span>
                <span class="badge accent-badge">${q.grade}</span>
            `;
            
            if (q.type === "篇章_閱讀") {
                tagsHtml += `<span class="badge accent-badge" style="background: rgba(0, 229, 255, 0.2); color: #fff;">📚 閱讀題組 (共 ${q.imagePaths.length - 1} 題)</span>`;
            } else {
                tagsHtml += `<span class="badge" style="background: rgba(130, 87, 229, 0.15); color: #c4b0ff;">${q.type}</span>`;
            }
            
            card.innerHTML = `
                ${imageBoxHtml}
                <div class="q-card-info">
                    <div class="q-card-tags">${tagsHtml}</div>
                    <div class="q-card-action">
                        <button class="secondary-btn small-btn btn-add-q" data-id="${q.id}">➕ 加入</button>
                    </div>
                </div>
            `;
            
            grid.appendChild(card);
            card.querySelectorAll('.preview-img-stacked').forEach(normalizeStackedPreviewImage);
        });
        
        // 綁定事件
        grid.querySelectorAll('.btn-add-q').forEach(btn => {
            btn.addEventListener('click', () => {
                const qId = btn.getAttribute('data-id');
                addQuestionToPaper(qId);
            });
        });
    }
    
    // 8. 新增單一題目至考卷
    function addQuestionToPaper(qId) {
        if (selectedQuestions.some(item => item.id === qId)) {
            showToast('此題目已在考卷清單中！', 'error');
            return;
        }
        
        const q = allQuestions.find(item => item.id === qId);
        if (q) {
            selectedQuestions.push(q);
            renderPaperList();
            showToast('已加入考卷清單');
            updateLabelsHighlight();
            
            // 同步更新對應題型的輸入框數值
            syncDrawInputs();
        }
    }
    
    // 同步抽幾題輸入框的數值
    function syncDrawInputs() {
        STANDARD_TYPES.forEach(type => {
            const count = selectedQuestions.filter(q => q.type === type).length;
            const drawInput = document.getElementById(`draw-input-${type}`);
            if (drawInput) {
                drawInput.value = count > 0 ? count : '';
            }
        });
    }
    
    // 9. 渲染已選考卷題目列表
    function renderPaperList() {
        const container = document.getElementById('paper-questions-list');
        const countSpan = document.getElementById('paper-q-count');
        const downloadBtn = document.getElementById('btn-download-word');
        
        countSpan.textContent = selectedQuestions.length;
        
        if (selectedQuestions.length === 0) {
            container.innerHTML = `
                <div class="empty-paper-placeholder">
                    <span class="placeholder-icon">📋</span>
                    <p>尚未選入題目<br>請使用隨機抽題，或從下方點選「➕ 加入」</p>
                </div>
            `;
            downloadBtn.disabled = true;
            return;
        }
        
        downloadBtn.disabled = false;
        container.innerHTML = '';
        
        selectedQuestions.forEach((q, index) => {
            const idx = index + 1;
            const item = document.createElement('div');
            item.className = 'paper-item';
            
            const firstImgPath = q.imagePaths && q.imagePaths.length > 0 ? q.imagePaths[0] : (q.imagePath || '');
            const typeLabel = q.type === "篇章_閱讀" ? "📚 閱讀題組" : q.type;
            
            item.innerHTML = `
                <div class="paper-item-idx">${idx}</div>
                <div class="paper-item-img" title="${typeLabel}">
                    <img src="${firstImgPath}" alt="題目">
                </div>
                <div class="paper-item-actions">
                    <button class="btn-move-up" data-idx="${index}" title="上移" ${index === 0 ? 'disabled style="opacity:0.2;"' : ''}>▲</button>
                    <button class="btn-move-down" data-idx="${index}" title="下移" ${index === selectedQuestions.length - 1 ? 'disabled style="opacity:0.2;"' : ''}>▼</button>
                    <button class="btn-remove-from-paper" data-idx="${index}" title="移除">✖</button>
                </div>
            `;
            container.appendChild(item);
        });
        
        // 綁定排序動作
        container.querySelectorAll('.btn-move-up').forEach(btn => {
            btn.addEventListener('click', () => {
                const idx = parseInt(btn.getAttribute('data-idx'));
                swapQuestions(idx, idx - 1);
            });
        });
        
        container.querySelectorAll('.btn-move-down').forEach(btn => {
            btn.addEventListener('click', () => {
                const idx = parseInt(btn.getAttribute('data-idx'));
                swapQuestions(idx, idx + 1);
            });
        });
        
        container.querySelectorAll('.btn-remove-from-paper').forEach(btn => {
            btn.addEventListener('click', () => {
                const idx = parseInt(btn.getAttribute('data-idx'));
                selectedQuestions.splice(idx, 1);
                renderPaperList();
                updateLabelsHighlight();
                syncDrawInputs();
            });
        });
    }
    
    function swapQuestions(idx1, idx2) {
        const temp = selectedQuestions[idx1];
        selectedQuestions[idx1] = selectedQuestions[idx2];
        selectedQuestions[idx2] = temp;
        renderPaperList();
    }
    
    // 10. 刪除題目 API 串接

    
    // 11. 隨機洗牌函式
    function shuffleArray(array) {
        let currentIndex = array.length, randomIndex;
        while (currentIndex !== 0) {
            randomIndex = Math.floor(Math.random() * currentIndex);
            currentIndex--;
            [array[currentIndex], array[randomIndex]] = [array[randomIndex], array[currentIndex]];
        }
        return array;
    }
    
    // 12. 綁定事件監聽器
    function setupGeneratorEvents() {
        // 科目與年級變更時重新篩選
        const filterGrade = document.getElementById('filter-grade');
        const filterSubject = document.getElementById('filter-subject');
        if (filterGrade) {
            filterGrade.addEventListener('change', () => {
                updateLabelsHighlight();
                filterAndRender();
            });
        }
        if (filterSubject) {
            filterSubject.addEventListener('change', () => {
                updateLabelsHighlight();
                updateDefaultTitle();
                filterAndRender();
            });
        }

        // 年份全選/全不選按鈕
        const btnToggleYears = document.getElementById('btn-toggle-all-years');
        btnToggleYears.addEventListener('click', () => {
            const checkboxes = document.querySelectorAll('.year-filter-cb');
            const anyUnchecked = Array.from(checkboxes).some(cb => !cb.checked);
            
            checkboxes.forEach(cb => {
                cb.checked = anyUnchecked;
            });
            
            btnToggleYears.textContent = anyUnchecked ? '全不選' : '全選';
            updateLabelsHighlight();
            updateDefaultTitle();
            filterAndRender();
        });
        
        // 清空考卷
        document.getElementById('btn-clear-paper').addEventListener('click', () => {
            selectedQuestions = [];
            renderPaperList();
            updateLabelsHighlight();
            syncDrawInputs();
            showToast('已清空考卷清單');
        });
        
        // 加全部符合條件的題目至考卷
        document.getElementById('btn-add-all').addEventListener('click', () => {
            const selectedYears = getSelectedYears();
            const selectedTypes = getSelectedTypes();
            const gradeVal = document.getElementById('filter-grade')?.value || '';
            const subjectVal = document.getElementById('filter-subject')?.value || '';
            
            if (!gradeVal || !subjectVal || selectedYears.length === 0) {
                showToast('請先選擇至少一個年度、科目與年級。', 'error');
                return;
            }
            const filtered = allQuestions.filter(q => {
                if (!selectedYears.includes(q.year)) return false;
                if (selectedTypes.length > 0 && !selectedTypes.includes(q.type)) return false;
                if (q.grade !== gradeVal || q.subject !== subjectVal) return false;
                return true;
            });
            
            let addedCount = 0;
            filtered.forEach(q => {
                if (!selectedQuestions.some(item => item.id === q.id)) {
                    selectedQuestions.push(q);
                    addedCount++;
                }
            });
            
            if (addedCount > 0) {
                renderPaperList();
                updateLabelsHighlight();
                syncDrawInputs();
                showToast(`已新增 ${addedCount} 題至考卷！`);
            } else {
                showToast('符合的題目早已全部在考卷中！');
            }
        });
        
        // 下載 Word 檔
        document.getElementById('btn-download-word').addEventListener('click', async () => {
            const title = document.getElementById('paper-title').value.trim();
            const subtitle = document.getElementById('paper-subtitle').value.trim();
            const sortOrder = document.getElementById('paper-sort-order').value;
            
            if (!title) {
                showToast('請填寫考卷大標題！', 'error');
                return;
            }
            
            let finalQuestions = [...selectedQuestions];
            
            if (sortOrder === 'year') {
                finalQuestions.sort((a, b) => {
                    const yearA = parseInt(a.year) || 0;
                    const yearB = parseInt(b.year) || 0;
                    if (yearA !== yearB) return yearA - yearB;
                    return a.id.localeCompare(b.id);
                });
            } else {
                // 隨機不分年份排列 (按照大題型分類排序，但在大題型內隨機排列)
                const groups = {};
                STANDARD_TYPES.forEach(type => {
                    groups[type] = [];
                });
                
                finalQuestions.forEach(q => {
                    if (groups[q.type]) {
                        groups[q.type].push(q);
                    } else {
                        if (!groups["字詞_應用"]) groups["字詞_應用"] = [];
                        groups["字詞_應用"].push(q);
                    }
                });
                
                let shuffledQuestions = [];
                STANDARD_TYPES.forEach(type => {
                    if (groups[type].length > 0) {
                        const shuffledGroup = shuffleArray([...groups[type]]);
                        shuffledQuestions = shuffledQuestions.concat(shuffledGroup);
                    }
                });
                
                finalQuestions = shuffledQuestions;
            }
            
            const questionIds = finalQuestions.map(q => q.id);
            const downloadBtn = document.getElementById('btn-download-word');
            downloadBtn.disabled = true;
            downloadBtn.querySelector('span').textContent = '正在打包 Word 中...';
            
            try {
                await window.exportQuestionsToWord(finalQuestions, title, subtitle);
                showToast('\u{1F389} Word \u8003\u5377\u4E0B\u8F09\u6210\u529F\uFF01');
            } catch (err) {
                console.error('Word \u532F\u51FA\u5931\u6557:', err);
                showToast('\u751F\u6210 Word \u5931\u6557\uFF0C\u8ACB\u91CD\u8A66\uFF01', 'error');
            } finally {
                downloadBtn.disabled = false;
                downloadBtn.querySelector('span').textContent = '\u{1F4E5} \u751F\u6210\u4E26\u4E0B\u8F09 Word \u6A94 (.docx)';
            }
        });
    }
})();
