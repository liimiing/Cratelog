'use strict';
document.querySelectorAll('.markdown-math').forEach(function (element) {
    if (typeof katex === 'undefined') return;
    katex.render(element.textContent, element, {
        displayMode: element.dataset.display === 'true',
        throwOnError: false,
        trust: false,
        maxExpand: 1000,
        maxSize: 20
    });
});
