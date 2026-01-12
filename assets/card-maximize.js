/**
 * Card Maximize/Minimize Functionality
 * Clientseitige Logik für das Vergrößern und Verkleinern von Kacheln
 */

(function() {
    'use strict';

    function init() {
        console.log('Card-Maximize.js: Initializing...');

        // Prüfen ob Buttons existieren
        var buttons = document.querySelectorAll('.card-maximize-btn');
        console.log('Card-Maximize.js: Found', buttons.length, 'maximize buttons');

        setupEventListeners();
    }

    function setupEventListeners() {
        // Event Delegation für Maximize-Buttons mit Capture-Phase
        document.addEventListener('click', function(e) {
            // Debug: Zeige geklicktes Element
            console.log('Click detected on:', e.target.tagName, e.target.className);

            // Suche nach dem Maximize-Button in der DOM-Hierarchie
            var btn = e.target.closest('.card-maximize-btn');

            if (btn) {
                console.log('Card-Maximize.js: Maximize button clicked!');
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();

                var card = btn.closest('.card');
                console.log('Card-Maximize.js: Found card:', card ? card.id : 'none');

                if (card) {
                    toggleCardMaximize(card, btn);
                }
                return false;
            }

            // Overlay-Klick schließt maximierte Kachel
            if (e.target.id === 'card-overlay' || e.target.classList.contains('card-overlay')) {
                console.log('Card-Maximize.js: Overlay clicked, closing...');
                closeAllMaximized();
            }
        }, true); // Capture-Phase für höhere Priorität

        // ESC-Taste schließt maximierte Kachel
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                console.log('Card-Maximize.js: ESC pressed, closing...');
                closeAllMaximized();
            }
        });

        console.log('Card-Maximize.js: Event listeners attached');
    }

    function toggleCardMaximize(card, btn) {
        console.log('Card-Maximize.js: toggleCardMaximize called for', card.id);

        var overlay = document.getElementById('card-overlay');
        var isMaximized = card.classList.contains('maximized');

        console.log('Card-Maximize.js: isMaximized =', isMaximized);

        if (isMaximized) {
            // === MINIMIZE ===
            console.log('Card-Maximize.js: Minimizing...');
            card.classList.remove('maximized');

            if (overlay) {
                overlay.classList.remove('active');
            }

            updateIcon(btn, false);

            // Charts nach kurzer Verzögerung neu rendern (mit normalen Schriften)
            setTimeout(function() {
                resizeChartsInCard(card, false);
            }, 100);

        } else {
            // === MAXIMIZE ===
            console.log('Card-Maximize.js: Maximizing...');
            closeAllMaximized();

            card.classList.add('maximized');
            console.log('Card-Maximize.js: Added maximized class. Classes now:', card.className);

            if (overlay) {
                overlay.classList.add('active');
                console.log('Card-Maximize.js: Activated overlay');
            } else {
                console.log('Card-Maximize.js: WARNING - overlay not found!');
            }

            updateIcon(btn, true);

            // Charts nach Animation neu rendern (mit größeren Schriften)
            setTimeout(function() {
                resizeChartsInCard(card, true);
            }, 350);
        }
    }

    function updateIcon(btn, isMaximized) {
        var expandIcon = btn.querySelector('.icon-expand');
        var shrinkIcon = btn.querySelector('.icon-shrink');

        if (expandIcon && shrinkIcon) {
            if (isMaximized) {
                expandIcon.style.display = 'none';
                shrinkIcon.style.display = 'flex';
            } else {
                expandIcon.style.display = 'flex';
                shrinkIcon.style.display = 'none';
            }
        }
    }

    function resizeChartsInCard(card, isMaximized) {
        var charts = card.querySelectorAll('.js-plotly-plot');
        charts.forEach(function(chart) {
            if (window.Plotly && typeof Plotly.Plots !== 'undefined') {
                try {
                    // Bei maximiertem Zustand: größere Schriften
                    if (isMaximized) {
                        Plotly.relayout(chart, {
                            'font.size': 14,
                            'xaxis.tickfont.size': 13,
                            'yaxis.tickfont.size': 13,
                            'xaxis.title.font.size': 14,
                            'yaxis.title.font.size': 14,
                            'legend.font.size': 13
                        });
                    } else {
                        // Zurück zu normalen Schriftgrößen
                        Plotly.relayout(chart, {
                            'font.size': 11,
                            'xaxis.tickfont.size': 10,
                            'yaxis.tickfont.size': 10,
                            'xaxis.title.font.size': 10,
                            'yaxis.title.font.size': 10,
                            'legend.font.size': 10
                        });
                    }
                    Plotly.Plots.resize(chart);
                    console.log('Card-Maximize.js: Resized chart, maximized:', isMaximized);
                } catch (e) {
                    console.log('Card-Maximize.js: Error resizing chart:', e);
                }
            }
        });
    }

    function closeAllMaximized() {
        var maximizedCards = document.querySelectorAll('.card.maximized');
        var overlay = document.getElementById('card-overlay');

        maximizedCards.forEach(function(card) {
            card.classList.remove('maximized');

            var btn = card.querySelector('.card-maximize-btn');
            if (btn) {
                updateIcon(btn, false);
            }

            setTimeout(function() {
                resizeChartsInCard(card, false);
            }, 100);
        });

        if (overlay) {
            overlay.classList.remove('active');
        }
    }

    // Initialisieren wenn DOM bereit
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Zusätzliche Initialisierung nach kurzer Verzögerung (für Dash-Komponenten)
    setTimeout(init, 500);
    setTimeout(init, 1500);

})();
