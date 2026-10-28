<?php
require_once __DIR__.'/cratelog_common.php';
if (session_status()===PHP_SESSION_NONE) {
    session_set_cookie_params(['httponly'=>true,'samesite'=>'Strict','secure'=>!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS']!=='off']);
    session_start();
}
if (!authorized((string)($_SESSION['cratelog_token'] ?? ''))) {
    header('Location: cratelog.php?login=1',true,303);exit;
}

// 语言检测与配置 / Language Detection & Config
$lang = 'en'; // Default
if (isset($_SERVER['HTTP_ACCEPT_LANGUAGE'])) {
    $acceptLang = substr($_SERVER['HTTP_ACCEPT_LANGUAGE'], 0, 2);
    if ($acceptLang === 'zh') {
        $lang = 'zh';
    }
}
// 强制通过参数覆盖（可选，用于调试）
if (isset($_GET['lang']) && in_array($_GET['lang'], ['zh', 'en'])) {
    $lang = $_GET['lang'];
}

$i18n = [
    'zh' => [
        'title' => 'HITLIKE 听觉考古',
        'title_suffix' => ' - 检索', // Page title suffix
        'placeholder' => '关键词...',
        'start_row_label' => '起始行:',
        'sort_asc' => '正序',
        'sort_desc' => '倒序',
        'btn_search' => '查询',
        'btn_reset' => '重置',
        'found_stats' => '找到 %d 条结果',
        'row_num' => '行号',
        'headers' => ['编号', '作者', '专辑', '年代', '厂牌', '版号', '风格', '载存', '备注'],
        'no_data' => '没有符合条件的记录',
        'loading' => '正在加载...',
        'end_text' => '已显示全部',
        'parse_fail' => '解析失败',
        'read_fail' => '工作表读取失败',
        'sheet_fail' => '工作表解析失败'
    ],
    'en' => [
        'title' => 'HITLIKE Auditory Archaeology',
        'title_suffix' => ' - Search',
        'placeholder' => 'Keywords...',
        'start_row_label' => 'Start Row:',
        'sort_asc' => 'Asc',
        'sort_desc' => 'Desc',
        'btn_search' => 'Search',
        'btn_reset' => 'Reset',
        'found_stats' => 'Found %d results',
        'row_num' => 'Row',
        'headers' => ['ID', 'Artist', 'Album', 'Year', 'Label', 'Catalog No', 'Genre', 'Format', 'Note'],
        'no_data' => 'No matching records found',
        'loading' => 'Loading...',
        'end_text' => 'All records loaded',
        'parse_fail' => 'Parse Failed',
        'read_fail' => 'Read Sheet Failed',
        'sheet_fail' => 'Parse Sheet Failed'
    ]
];
$t = $i18n[$lang];

// 修复后的解析函数
function parseXLSX($file, $t_errors)
{
    $zip = new ZipArchive();
    if ($zip->open($file) !== TRUE) {
        return [[$t_errors['parse_fail']]];
    }

    // 读取共享字符串
    $sharedStringXml = $zip->getFromName('xl/sharedStrings.xml');
    $sharedStrings = [];
    if ($sharedStringXml) {
        $sst = simplexml_load_string($sharedStringXml);
        if ($sst) {
            foreach ($sst->si as $si) {
                if (isset($si->t)) {
                    $sharedStrings[] = (string)$si->t;
                } elseif (isset($si->r)) {
                    $text = '';
                    foreach ($si->r as $r) {
                        $text .= (string)$r->t;
                    }
                    $sharedStrings[] = $text;
                } else {
                    $sharedStrings[] = '';
                }
            }
        }
    }

    $sheetXml = $zip->getFromName('xl/worksheets/sheet1.xml');
    if (!$sheetXml) {
        $zip->close();
        return [[$t_errors['read_fail']]];
    }

    $sheet = simplexml_load_string($sheetXml);
    if (!$sheet) {
        $zip->close();
        return [[$t_errors['sheet_fail']]];
    }

    $rows = [];

    foreach ($sheet->sheetData->row as $rowNode) {
        $rowData = [];

        foreach ($rowNode->c as $cell) {
            $cellRef = (string)$cell['r'];
            $col = columnIndexFromCellRef($cellRef);

            $value = '';
            if (isset($cell->v)) {
                $cellValue = (string)$cell->v;
                $cellType = (string)($cell['t'] ?? '');

                if ($cellType === 's') {
                    $index = (int)$cellValue;
                    $value = isset($sharedStrings[$index]) ? $sharedStrings[$index] : '';
                } elseif ($cellType === 'inlineStr' && isset($cell->is->t)) {
                    $value = (string)$cell->is->t;
                } elseif ($cellType === 'str') {
                    $value = $cellValue;
                } else {
                    $value = $cellValue;
                }
            } elseif (isset($cell->is->t)) {
                $value = (string)$cell->is->t;
            }

            $rowData[$col] = $value;
        }

        for ($i = 0; $i < 9; $i++) {
            if (!isset($rowData[$i])) {
                $rowData[$i] = '';
            }
        }
        ksort($rowData);
        $rows[] = array_values($rowData);
    }

    $zip->close();
    // 假设第一行是标题，如果不是，需要调整
    // 但根据原代码，第一行似乎被切片 slice(1) 去掉了，所以这里返回全部
    return $rows;
}

function columnIndexFromCellRef($cellRef)
{
    preg_match('/^([A-Z]+)/', $cellRef, $matches);
    if (!isset($matches[1])) return 0;

    $col = $matches[1];
    $index = 0;
    for ($i = 0; $i < strlen($col); $i++) {
        $index = $index * 26 + (ord($col[$i]) - ord('A') + 1);
    }
    return $index - 1;
}

function highlightText($text, $query)
{
    if (!$query) {
        return htmlspecialchars($text);
    }
    // 简单的关键词高亮，不区分大小写
    return preg_replace_callback(
        '/' . preg_quote($query, '/') . '/iu',
        function ($matches) {
            return '<span class="highlight">' . htmlspecialchars($matches[0]) . '</span>';
        },
        htmlspecialchars($text)
    );
}

// 初始化数据
// 缓存机制可以优化（例如存文件或session），但这里保持无状态
$records = parseXLSX('Records.xlsx', $t);
$headers = $t['headers'];

// 去掉Excel表头行（原代码 array_slice($records, 1)）
$data = array_slice($records, 1);

// 获取参数
$query = $_GET['q'] ?? '';
$startRow = isset($_GET['start_row']) ? max(1, (int)$_GET['start_row']) : 1;
$page = isset($_GET['page']) ? max(1, (int)$_GET['page']) : 1;
$order = $_GET['order'] ?? 'desc'; // 'asc' or 'desc'
$perPage = 20;

// 过滤数据
$filtered = [];
if ($query) {
    foreach ($data as $row) {
        $match = false;
        foreach ($row as $cell) {
            if (stripos($cell ?? '', $query) !== false) {
                $match = true;
                break;
            }
        }
        if ($match) {
            $filtered[] = $row;
        }
    }
} else {
    $filtered = $data;
}

// 排序处理
if ($order === 'desc') {
    $filtered = array_reverse($filtered);
}

$total = count($filtered);

// 计算偏移量
$baseOffset = $startRow - 1;
$currentOffset = $baseOffset + ($page - 1) * $perPage;

// 确保偏移量不超过总数
if ($currentOffset > $total) {
    $currentOffset = $total;
}

// 切片获取当前页数据
// 如果 Start Row 很大，可能这就为空了
$currentPageData = array_slice($filtered, $currentOffset, $perPage);

// 此时是否还有更多数据？
$isLastPage = ($currentOffset + count($currentPageData)) >= $total;

$isAjax = isset($_SERVER['HTTP_X_REQUESTED_WITH']) && $_SERVER['HTTP_X_REQUESTED_WITH'] === 'XMLHttpRequest';

if ($isAjax) {
    header('Content-Type: application/json');
    $rowsPayload = [];
    foreach ($currentPageData as $i => $row) {
        $rowsPayload[] = [
            'num' => $currentOffset + $i + 1,
            'cells' => $row
        ];
    }
    echo json_encode([
        'success' => true,
        'rows' => $rowsPayload,
        'page' => $page,
        'hasMore' => !$isLastPage,
        'total' => $total
    ]);
    exit;
}
?>
<!DOCTYPE html>
<html lang="<?php echo $lang; ?>">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?php echo htmlspecialchars($t['title'] . $t['title_suffix']); ?></title>
    <style>
        /* 基础重置 */
        * {
            box-sizing: border-box;
            /* 关键：统一盒模型，防止宽度计算偏差 */
        }

        body {
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            background-color: #f5f5f5;
            color: #333;
            margin: 0;
            padding: 20px;
            font-size: 14px;
            line-height: 1.5;
        }

        h1 {
            text-align: center;
            font-size: 24px;
            color: #444;
            margin-bottom: 20px;
            font-weight: normal;
        }

        /* 容器 */
        .container {
            max-width: 1200px;
            margin: 0 auto;
            position: relative;
            /* For sticky context */
        }

        /* 搜索区域 */
        .search-area {
            background: #eee;
            padding: 20px;
            border-radius: 4px;
            margin-bottom: 20px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            align-items: center;
            justify-content: center;
            transition: all 0.3s ease;
            z-index: 1000;
        }

        /* 紧凑固定模式 */
        .search-area.compact {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            margin: 0;
            border-radius: 0;
            padding: 8px 10px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            background: rgba(238, 238, 238, 0.95);
            backdrop-filter: blur(5px);
            border-bottom: 1px solid #ddd;
        }

        /* 占位符，防止搜索栏fixed后内容上跳 */
        .search-placeholder {
            display: none;
            height: 80px;
            /* Approximate height */
        }

        .search-group {
            display: flex;
            align-items: center;
            gap: 5px;
        }

        input[type="text"],
        input[type="number"] {
            border: 1px solid #ccc;
            padding: 8px 10px;
            border-radius: 3px;
            outline: none;
        }

        /* 紧凑模式下的输入框微调 */
        .search-area.compact input[type="text"],
        .search-area.compact input[type="number"] {
            padding: 5px 8px;
            font-size: 13px;
        }

        .search-area.compact .search-stats {
            display: none;
        }

        input[type="text"]:focus,
        input[type="number"]:focus {
            border-color: #666;
        }

        input[type="text"] {
            width: 200px;
        }

        input[type="number"] {
            width: 80px;
        }

        .radio-group {
            display: flex;
            gap: 10px;
            margin: 0 5px;
        }

        .radio-group label {
            display: flex;
            align-items: center;
            gap: 4px;
            cursor: pointer;
            font-size: 13px;
            color: #555;
        }

        button {
            border: none;
            cursor: pointer;
            padding: 9px 18px;
            border-radius: 3px;
            font-size: 14px;
            transition: background 0.2s;
        }

        .search-area.compact button {
            padding: 6px 12px;
            font-size: 13px;
        }

        .btn-search {
            width: 200px;
            background-color: #333;
            color: #fff;
        }

        .btn-search:hover {
            background-color: #555;
        }

        .btn-reset {
            width: 200px;
            background-color: #ddd;
            color: #333;
        }

        .btn-reset:hover {
            background-color: #ccc;
        }

        .search-stats {
            width: 100%;
            text-align: center;
            font-size: 12px;
            color: #666;
            margin-top: 5px;
        }

        /* 表格 */
        .table-responsive {
            overflow-x: auto;
            margin-bottom: 20px;
            /* Update: Ensure relative positioning so we can track it */
            position: relative;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            min-width: 800px;
            background: #fff;
            table-layout: auto;
            /* Allow auto layout */
        }

        #mainTable {
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        }

        thead {
            background-color: #f9f9f9;
        }

        th,
        td {
            text-align: left;
            padding: 12px;
            border-bottom: 1px solid #ddd;
        }

        th {
            font-weight: 600;
            color: #555;
            white-space: nowrap;
        }

        .col-row-num {
            width: 52px;
            min-width: 52px;
            max-width: 52px;
            text-align: center;
            color: #888;
            white-space: nowrap;
        }

        /* 悬停表头容器 */
        .sticky-header-container {
            position: fixed;
            top: 0;
            left: 0;
            display: none;
            z-index: 999;
            overflow: hidden;
            background: #f9f9f9;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            border-bottom: 1px solid #ddd;
            /* Match standard border */
        }

        .sticky-header-container table {
            margin-bottom: 0;
        }

        /* 斑马纹 */
        tbody tr:nth-child(even) {
            background-color: #fcfcfc;
        }

        tbody tr:hover {
            background-color: #f0f0f0;
        }

        /* 高亮 */
        .highlight {
            background-color: #fffacd;
            color: #333;
            padding: 0 2px;
            border-radius: 2px;
            font-weight: bold;
        }

        /* 加载 / 底部提示 */
        .loading-container {
            text-align: center;
            padding: 20px 0;
            color: #999;
            font-size: 13px;
            min-height: 40px;
        }

        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid #ccc;
            border-top-color: #333;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin-right: 8px;
            vertical-align: middle;
        }

        @keyframes spin {
            to {
                transform: rotate(360deg);
            }
        }

        .no-data {
            text-align: center;
            padding: 40px;
            color: #999;
        }

        /* 移动端适配 */
        @media (max-width: 600px) {
            .search-area {
                flex-direction: column;
                align-items: stretch;
            }

            .search-area.compact {
                flex-direction: row;
                flex-wrap: nowrap;
                overflow-x: auto;
                justify-content: flex-start;
            }

            .search-area.compact input {
                width: 100px !important;
            }

            .radio-group {
                justify-content: center;
                margin: 10px 0;
            }

            .search-area.compact .radio-group {
                margin: 0;
                font-size: 12px;
                flex-shrink: 0;
            }
        }
    </style>
</head>

<body>

    <div class="container">
        <h1 id="pageTitle"><?php echo htmlspecialchars($t['title']); ?></h1>

        <div class="search-placeholder" id="searchPlaceholder"></div>
        <p><a href="cratelog.php">Cratelog · 专辑封面、评分与曲目标记</a></p>
        <form class="search-area" id="searchForm" method="GET" action="">
            <div class="search-group">
                <input type="text" name="q" id="query" placeholder="<?php echo htmlspecialchars($t['placeholder']); ?>" value="<?php echo htmlspecialchars($query); ?>">
            </div>

            <div class="search-group">
                <label for="start_row" style="font-size:12px; color:#666;"><?php echo htmlspecialchars($t['start_row_label']); ?></label>
                <input type="number" name="start_row" id="start_row" placeholder="1" value="<?php echo htmlspecialchars($startRow); ?>" min="1">
            </div>

            <div class="search-group">
                <div class="radio-group">
                    <label>
                        <input type="radio" name="order" value="asc" <?php echo $order === 'asc' ? 'checked' : ''; ?>> <?php echo htmlspecialchars($t['sort_asc']); ?>
                    </label>
                    <label>
                        <input type="radio" name="order" value="desc" <?php echo $order === 'desc' ? 'checked' : ''; ?>> <?php echo htmlspecialchars($t['sort_desc']); ?>
                    </label>
                </div>
            </div>

            <div class="search-group" style="flex:1; justify-content: center; gap: 10px;">
                <button type="submit" class="btn-search"><?php echo htmlspecialchars($t['btn_search']); ?></button>
                <button type="button" class="btn-reset" id="btnReset"><?php echo htmlspecialchars($t['btn_reset']); ?></button>
            </div>
            <div class="search-stats">
                <?php echo sprintf($t['found_stats'], $total); ?>
            </div>
        </form>

        <!-- 悬停表头容器 -->
        <div id="stickyHeaderContainer" class="sticky-header-container"></div>

        <div class="table-responsive" id="tableContainer">
            <table id="mainTable">
                <thead>
                    <tr>
                        <th class="col-row-num"><?php echo htmlspecialchars($t['row_num']); ?></th>
                        <?php foreach ($headers as $h): ?>
                            <th><?php echo htmlspecialchars($h); ?></th>
                        <?php endforeach; ?>
                    </tr>
                </thead>
                <tbody id="resultBody">
                    <?php if (count($currentPageData) === 0): ?>
                        <tr>
                            <td colspan="<?php echo count($headers) + 1; ?>" class="no-data"><?php echo htmlspecialchars($t['no_data']); ?></td>
                        </tr>
                    <?php else: ?>
                        <?php foreach ($currentPageData as $i => $row): ?>
                            <tr>
                                <td class="col-row-num"><?php echo $currentOffset + $i + 1; ?></td>
                                <?php foreach ($row as $cell): ?>
                                    <td><?php echo highlightText($cell ?? '', $query); ?></td>
                                <?php endforeach; ?>
                            </tr>
                        <?php endforeach; ?>
                    <?php endif; ?>
                </tbody>
            </table>
        </div>

        <div class="loading-container" id="loadingContainer">
            <?php if (!$isLastPage && count($currentPageData) > 0): ?>
                <div id="loadingText" style="display:none;"><span class="spinner"></span> <?php echo htmlspecialchars($t['loading']); ?></div>
                <div id="endText" style="display:none;"><?php echo htmlspecialchars($t['end_text']); ?></div>
            <?php else: ?>
                <span><?php echo htmlspecialchars($t['end_text']); ?></span>
            <?php endif; ?>
        </div>
    </div>

    <script>
        document.addEventListener('DOMContentLoaded', function() {
            // DOM Elements
            const searchForm = document.getElementById('searchForm');
            const searchPlaceholder = document.getElementById('searchPlaceholder');
            const pageTitle = document.getElementById('pageTitle');
            const mainTable = document.getElementById('mainTable');
            const tableContainer = document.getElementById('tableContainer');
            const stickyHeaderContainer = document.getElementById('stickyHeaderContainer');

            const loadingContainer = document.getElementById('loadingContainer');
            const loadingText = document.getElementById('loadingText');
            const endText = document.getElementById('endText');
            const resultBody = document.getElementById('resultBody');
            const btnReset = document.getElementById('btnReset');

            // State
            let currentPage = <?php echo $page; ?>;
            let query = "<?php echo addslashes($query); ?>";
            let startRow = <?php echo $startRow; ?>;
            let order = "<?php echo $order; ?>";
            let isLoading = false;
            let hasMore = <?php echo $isLastPage ? 'false' : 'true'; ?>;

            // --- Sticky Logic ---

            let originalThead = mainTable.querySelector('thead');
            let stickyTable = null;
            let stickyThs = [];
            let originalThs = [];

            // Clone Header
            if (originalThead) {
                stickyTable = document.createElement('table');
                let clonedThead = originalThead.cloneNode(true);
                stickyTable.appendChild(clonedThead);
                stickyHeaderContainer.appendChild(stickyTable);

                stickyThs = clonedThead.querySelectorAll('th');
                originalThs = originalThead.querySelectorAll('th');
            }

            function syncHeader() {
                if (!stickyTable || !originalThs.length) return;

                // 1. Sync Widths
                // Use getBoundingClientRect for precise sub-pixel measurements
                // Important: Clone the width of the TABLE itself first
                stickyTable.style.width = mainTable.getBoundingClientRect().width + 'px';

                // Sync Container to limit output (though visible area is limited by viewport effectively if fixed)
                // But horizontal scroll relies on container sizing.
                // stickyHeaderContainer.style.width = tableContainer.clientWidth + 'px'; 

                originalThs.forEach((th, index) => {
                    if (stickyThs[index]) {
                        // Use getBoundingClientRect().width which includes border+padding (if box-sizing: border-box)
                        const rect = th.getBoundingClientRect();
                        stickyThs[index].style.width = rect.width + 'px';
                        stickyThs[index].style.minWidth = rect.width + 'px';
                        stickyThs[index].style.maxWidth = rect.width + 'px';
                        stickyThs[index].style.boxSizing = 'border-box'; // Ensure sticky frame matches
                    }
                });

                // 2. Sync Horizontal Scroll
                stickyHeaderContainer.scrollLeft = tableContainer.scrollLeft;
            }

            // Scroll Handler for Sticky Effects
            window.addEventListener('scroll', () => {
                const scrollY = window.scrollY;
                const threshold = pageTitle.offsetHeight + 10;

                // A. Search Bar Sticky
                if (scrollY > threshold) {
                    searchForm.classList.add('compact');
                    searchPlaceholder.style.display = 'block';
                    searchPlaceholder.style.height = searchForm.offsetHeight + 'px';
                } else {
                    searchForm.classList.remove('compact');
                    searchPlaceholder.style.display = 'none';
                }

                // B. Table Header Sticky
                const tableRect = mainTable.getBoundingClientRect();
                const searchHeight = searchForm.offsetHeight;
                const containerRect = tableContainer.getBoundingClientRect();

                if (searchForm.classList.contains('compact')) {
                    stickyHeaderContainer.style.top = searchHeight + 'px';

                    // logic: sticky header visible if table top is above visible area (scrolled past)
                    // AND table bottom is still in view
                    if (tableRect.top < searchHeight && tableRect.bottom > searchHeight) {
                        stickyHeaderContainer.style.display = 'block';

                        // Sync container position/width
                        stickyHeaderContainer.style.left = containerRect.left + 'px';
                        stickyHeaderContainer.style.width = containerRect.width + 'px';

                        // Always sync header on scroll show to be safe? 
                        // Performance cost is low for just checking widths
                        // but ResizeObserver handles the size changes better.
                        // syncHeader(); 
                    } else {
                        stickyHeaderContainer.style.display = 'none';
                    }
                } else {
                    stickyHeaderContainer.style.display = 'none';
                }

                // C. Infinite Scroll Load
                if (!isLoading && hasMore) {
                    if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 100) {
                        loadMore();
                    }
                }
            });

            // Sync on Resize
            window.addEventListener('resize', syncHeader);

            // Watch for changes in table size (content added)
            if (window.ResizeObserver) {
                const resizeObserver = new ResizeObserver(entries => {
                    for (let entry of entries) {
                        syncHeader();
                    }
                });
                resizeObserver.observe(mainTable);
            }

            // Table horizontal scroll sync
            tableContainer.addEventListener('scroll', () => {
                stickyHeaderContainer.scrollLeft = tableContainer.scrollLeft;
            });

            // --- End Sticky Logic ---

            // Reset
            if (btnReset) {
                btnReset.addEventListener('click', function() {
                    document.getElementById('query').value = '';
                    document.getElementById('start_row').value = '';
                    const radios = document.getElementsByName('order');
                    for (let r of radios)
                        if (r.value === 'desc') r.checked = true;
                    // Reset sticky? Page will reload.
                    searchForm.submit();
                });
            }

            // Initial load check
            if (document.body.offsetHeight <= window.innerHeight && hasMore) {
                loadMore();
            }

            function loadMore() {
                if (isLoading || !hasMore) return;

                isLoading = true;
                if (loadingText) loadingText.style.display = 'block';

                const nextPage = currentPage + 1;
                const url = `?q=${encodeURIComponent(query)}&start_row=${startRow}&order=${order}&page=${nextPage}`;

                fetch(url, {
                        headers: {
                            'X-Requested-With': 'XMLHttpRequest'
                        }
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success && data.rows.length > 0) {
                            data.rows.forEach(row => {
                                const tr = document.createElement('tr');
                                const numTd = document.createElement('td');
                                numTd.className = 'col-row-num';
                                numTd.textContent = row.num;
                                tr.appendChild(numTd);
                                row.cells.forEach(cell => {
                                    const td = document.createElement('td');
                                    let content = escapeHtml(cell || '');
                                    if (query) {
                                        const regex = new RegExp('(' + escapeRegex(query) + ')', 'gi');
                                        content = content.replace(regex, '<span class="highlight">$1</span>');
                                    }
                                    td.innerHTML = content;
                                    tr.appendChild(td);
                                });
                                resultBody.appendChild(tr);
                            });

                            currentPage = nextPage;

                            // ResizeObserver will catch the change and trigger syncHeader

                            if (!data.hasMore) {
                                hasMore = false;
                                if (loadingText) loadingText.style.display = 'none';
                                if (endText) endText.style.display = 'block';
                            }
                        } else {
                            hasMore = false;
                            if (loadingText) loadingText.style.display = 'none';
                            if (endText) endText.style.display = 'block';
                        }
                    })
                    .catch(err => {
                        console.error('List load failed', err);
                    })
                    .finally(() => {
                        isLoading = false;
                        if (hasMore && document.body.offsetHeight <= window.innerHeight) {
                            loadMore();
                        } else {
                            if (loadingText && hasMore) loadingText.style.display = 'none';
                        }
                    });
            }

            function escapeHtml(text) {
                if (!text) return '';
                return text
                    .replace(/&/g, "&amp;")
                    .replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;")
                    .replace(/"/g, "&quot;")
                    .replace(/'/g, "&#039;");
            }

            function escapeRegex(string) {
                return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            }
        });
    </script>
</body>

</html>
