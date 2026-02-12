// Mobile Navigation Toggle
const navToggle = document.querySelector('.nav-toggle');
const navMenu = document.querySelector('.nav-menu');

if (navToggle) {
    navToggle.addEventListener('click', () => {
        navMenu.classList.toggle('active');
    });
}

// Close mobile menu when clicking on a link
const navLinks = document.querySelectorAll('.nav-menu a');
navLinks.forEach(link => {
    link.addEventListener('click', () => {
        navMenu.classList.remove('active');
    });
});

// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// Global variables
let leaderboardData = null;
let currentTab = 'overall';
let currentFilter = 'all';

// Load leaderboard data and render tables
async function loadLeaderboardData() {
    const tbodyOverall = document.getElementById('leaderboard-body-overall');
    const tbodyAfterCutoff = document.getElementById('leaderboard-body-aftercutoff');
    
    if (!tbodyOverall || !tbodyAfterCutoff) {
        console.error('Leaderboard table bodies not found');
        return;
    }
    
    // Show loading state
    tbodyOverall.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-secondary); padding: 2rem;">Loading leaderboard data...</td></tr>';
    tbodyAfterCutoff.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-secondary); padding: 2rem;">Loading leaderboard data...</td></tr>';
    
    try {
        // Try multiple possible paths
        let response;
        const paths = [
            'data/leaderboard.json',
            './data/leaderboard.json',
            '/data/leaderboard.json',
            'https://github.com/ZhilingYan/LiveMedBench/raw/main/website/data/leaderboard.json'
        ];
        
        let data = null;
        for (const path of paths) {
            try {
                response = await fetch(path);
                if (response.ok) {
                    data = await response.json();
                    console.log('Loaded leaderboard from:', path);
                    break;
                }
            } catch (e) {
                console.log('Failed to load from:', path, e);
                continue;
            }
        }
        
        if (!data || !data.models) {
            throw new Error('Invalid data format or file not found');
        }
        
        leaderboardData = data;
        
        // Update last updated date
        const lastUpdatedEl = document.getElementById('last-updated');
        if (lastUpdatedEl && data.last_updated) {
            lastUpdatedEl.textContent = data.last_updated;
        }
        
        // Render both tables
        renderTables();
        
        // Setup tabs and filters
        setupTabs();
        setupFilters();
        
        console.log('Leaderboard loaded successfully:', data.models.length, 'models');
    } catch (error) {
        console.error('Failed to load leaderboard data:', error);
        const errorMsg = `<tr><td colspan="4" style="text-align: center; color: var(--text-secondary); padding: 2rem;">
            Failed to load leaderboard data. Please check the console for details.<br>
            <small>Error: ${error.message}</small>
        </td></tr>`;
        tbodyOverall.innerHTML = errorMsg;
        tbodyAfterCutoff.innerHTML = errorMsg;
    }
}

// Render both leaderboard tables
function renderTables() {
    if (!leaderboardData) return;
    
    // Sort models by current tab's score
    const sortedModels = [...leaderboardData.models].sort((a, b) => {
        const scoreA = currentTab === 'overall' ? a.overall : a.after_cutoff;
        const scoreB = currentTab === 'overall' ? b.overall : b.after_cutoff;
        return scoreB - scoreA;
    });
    
    // Re-rank based on sorted order
    sortedModels.forEach((model, index) => {
        model.currentRank = index + 1;
    });
    
    // Render Overall table
    renderTable('overall', sortedModels);
    
    // Sort for After Cutoff
    const sortedAfterCutoff = [...leaderboardData.models].sort((a, b) => b.after_cutoff - a.after_cutoff);
    sortedAfterCutoff.forEach((model, index) => {
        model.afterCutoffRank = index + 1;
    });
    
    // Render After Cutoff table
    renderTable('aftercutoff', sortedAfterCutoff);
}

// Render a single table
function renderTable(type, models) {
    const tbody = document.getElementById(`leaderboard-body-${type}`);
    if (!tbody) return;
    
    tbody.innerHTML = '';
    
    models.forEach(model => {
        const row = document.createElement('tr');
        
        // Build data attributes for filtering
        const dataAttrs = [];
        if (model.type === 'Proprietary') dataAttrs.push('api');
        if (model.type === 'Open Access') dataAttrs.push('open');
        if (model.is_medical) dataAttrs.push('medical');
        row.setAttribute('data-filter', dataAttrs.join(' '));
        
        // Highlight top 3 models
        const rank = type === 'overall' ? model.currentRank : model.afterCutoffRank;
        if (rank <= 3) {
            row.classList.add(`top-${rank}`);
        }
        
        const score = type === 'overall' ? model.overall : model.after_cutoff;
        const displayRank = type === 'overall' ? model.currentRank : model.afterCutoffRank;
        
        // Build type display with medical badge
        let typeDisplay = model.type;
        if (model.is_medical) {
            typeDisplay += ' <span class="medical-badge">Med</span>';
        }
        
        // Add rank change indicator for after cutoff table
        let rankChangeIndicator = '';
        if (type === 'aftercutoff') {
            const overallRank = model.currentRank;
            const afterCutoffRank = model.afterCutoffRank;
            const rankDiff = overallRank - afterCutoffRank;
            
            if (rankDiff > 0) {
                // Rank improved (went up)
                rankChangeIndicator = ` <span class="rank-change up" title="Rank improved by ${rankDiff}">↑${rankDiff}</span>`;
            } else if (rankDiff < 0) {
                // Rank declined (went down)
                rankChangeIndicator = ` <span class="rank-change down" title="Rank declined by ${Math.abs(rankDiff)}">↓${Math.abs(rankDiff)}</span>`;
            } else {
                // Rank unchanged
                rankChangeIndicator = ` <span class="rank-change unchanged" title="Rank unchanged">=</span>`;
            }
        }
        
        row.innerHTML = `
            <td>${displayRank}${rankChangeIndicator}</td>
            <td><strong>${model.name}</strong></td>
            <td>${typeDisplay}</td>
            <td><strong>${(score * 100).toFixed(2)}%</strong></td>
        `;
        
        tbody.appendChild(row);
    });
    
    // Apply current filter
    applyFilter();
}

// Setup tab switching
function setupTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    const overallTable = document.getElementById('overall-table');
    const afterCutoffTable = document.getElementById('aftercutoff-table');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            // Remove active class from all tabs
            tabButtons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');
            
            // Switch tables
            currentTab = button.getAttribute('data-tab');
            if (currentTab === 'overall') {
                overallTable.style.display = 'block';
                afterCutoffTable.style.display = 'none';
                // Scroll to top
                if (overallTable) overallTable.scrollTop = 0;
            } else {
                overallTable.style.display = 'none';
                afterCutoffTable.style.display = 'block';
                // Scroll to top
                if (afterCutoffTable) afterCutoffTable.scrollTop = 0;
            }
            
            // Re-apply filter
            applyFilter();
        });
    });
}

// Setup filter buttons
function setupFilters() {
    const filterButtons = document.querySelectorAll('.filter-btn');
    
    filterButtons.forEach(button => {
        button.addEventListener('click', () => {
            // Remove active class from all buttons
            filterButtons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');
            
            currentFilter = button.getAttribute('data-filter');
            applyFilter();
        });
    });
}

// Apply current filter to visible table
function applyFilter() {
    const visibleTable = currentTab === 'overall' ? 
        document.getElementById('leaderboard-body-overall') : 
        document.getElementById('leaderboard-body-aftercutoff');
    
    if (!visibleTable) return;
    
    const rows = visibleTable.querySelectorAll('tr');
    
    rows.forEach(row => {
        const rowFilters = row.getAttribute('data-filter') || '';
        
        if (currentFilter === 'all') {
            row.style.display = '';
        } else if (currentFilter === 'api' && rowFilters.includes('api')) {
            row.style.display = '';
        } else if (currentFilter === 'open' && rowFilters.includes('open')) {
            row.style.display = '';
        } else if (currentFilter === 'medical' && rowFilters.includes('medical')) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
}

// Intersection Observer for fade-in animations
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = '1';
            entry.target.style.transform = 'translateY(0)';
        }
    });
}, observerOptions);

// Observe feature cards and other sections
document.querySelectorAll('.feature-card, .evaluation-step, .download-card').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(20px)';
    el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
    observer.observe(el);
});

// Call on page load - wait for DOM to be ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadLeaderboardData);
} else {
    // DOM is already ready
    loadLeaderboardData();
}

// Add active state to navigation based on scroll position
window.addEventListener('scroll', () => {
    const sections = document.querySelectorAll('section[id]');
    const scrollY = window.pageYOffset;

    sections.forEach(section => {
        const sectionHeight = section.offsetHeight;
        const sectionTop = section.offsetTop - 100;
        const sectionId = section.getAttribute('id');

        if (scrollY > sectionTop && scrollY <= sectionTop + sectionHeight) {
            navLinks.forEach(link => {
                link.classList.remove('active');
                if (link.getAttribute('href') === `#${sectionId}`) {
                    link.classList.add('active');
                }
            });
        }
    });
});
