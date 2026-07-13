(function () {
    const {
        Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell,
        AlignmentType, WidthType, BorderStyle, SectionType
    } = window.docx;

    // A3 portrait (297 × 420 mm), two columns.
    const A3_WIDTH = 16838;
    const A3_HEIGHT = 23811;
    const MARGIN = 864;
    // The wider A3 column lets every source image be 22% larger than B4.
    const MAX_IMAGE_WIDTH = 500;
    const SOURCE_COLUMN_WIDTH = 1000;

    async function loadImage(path) {
        const response = await fetch(path, { cache: 'reload' });
        if (!response.ok) throw new Error(`無法載入題目圖片：${path}`);
        const blob = await response.blob();
        const bytes = new Uint8Array(await blob.arrayBuffer());
        const size = await readImageSize(blob);
        // Keep a stable source-pixel scale. A narrowly trimmed image must not
        // be enlarged more than a full-width image, otherwise text sizes jump.
        const width = Math.max(1, Math.min(
            MAX_IMAGE_WIDTH,
            Math.round(size.width * MAX_IMAGE_WIDTH / SOURCE_COLUMN_WIDTH)
        ));
        const height = Math.max(1, Math.round(size.height * width / size.width));
        return new ImageRun({ data: bytes, type: 'png', transformation: { width, height } });
    }

    async function readImageSize(blob) {
        if ('createImageBitmap' in window) {
            const bitmap = await createImageBitmap(blob);
            const size = { width: bitmap.width, height: bitmap.height };
            bitmap.close();
            return size;
        }
        return new Promise((resolve, reject) => {
            const url = URL.createObjectURL(blob);
            const image = new Image();
            image.onload = () => {
                const size = { width: image.naturalWidth, height: image.naturalHeight };
                URL.revokeObjectURL(url);
                resolve(size);
            };
            image.onerror = () => { URL.revokeObjectURL(url); reject(new Error('圖片尺寸讀取失敗')); };
            image.src = url;
        });
    }

    function textRun(text, options = {}) {
        return new TextRun({ text, font: 'DFKai-SB', ...options });
    }

    function infoTable() {
        const border = { style: BorderStyle.SINGLE, size: 6, color: '777777' };
        return new Table({
            width: { size: 100, type: WidthType.PERCENTAGE },
            rows: [new TableRow({
                children: ['班級：', '座號：', '姓名：', '得分：'].map(label => new TableCell({
                    borders: { top: border, bottom: border, left: border, right: border },
                    children: [new Paragraph({ spacing: { before: 120, after: 120 }, children: [textRun(label, { size: 32 })] })]
                }))
            })]
        });
    }

    async function questionParagraphs(questions) {
        const children = [];
        for (const question of questions) {
            const paths = question.imagePaths?.length ? question.imagePaths : [question.imagePath].filter(Boolean);
            for (const path of paths) {
                const image = await loadImage(path);
                children.push(new Paragraph({ alignment: AlignmentType.LEFT, spacing: { after: 120 }, children: [image] }));
            }
        }
        return children;
    }

    function safeFilename(name) {
        return (name || '歷屆篩選測驗').replace(/[\\/:*?"<>|]/g, '-').slice(0, 100) + '.docx';
    }

    function download(blob, filename) {
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    window.exportQuestionsToWord = async function (questions, title, subtitle) {
        if (!questions.length) throw new Error('尚未選擇題目');
        const body = await questionParagraphs(questions);
        const titleChildren = [
            new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 }, children: [textRun(title, { bold: true, size: title.length > 36 ? 30 : 42 })] })
        ];
        if (subtitle) {
            titleChildren.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: [textRun(subtitle, { size: 24 })] }));
        }
        titleChildren.push(infoTable(), new Paragraph({ spacing: { after: 80 }, children: [] }));

        const doc = new Document({
            sections: [
                {
                    properties: { page: { size: { width: A3_WIDTH, height: A3_HEIGHT }, margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN } } },
                    children: titleChildren
                },
                {
                    properties: {
                        type: SectionType.CONTINUOUS,
                        page: { size: { width: A3_WIDTH, height: A3_HEIGHT }, margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN } },
                        column: { count: 2, space: 576, equalWidth: true, separate: true }
                    },
                    children: body
                }
            ]
        });
        const blob = await Packer.toBlob(doc);
        download(blob, safeFilename(title));
    };
})();