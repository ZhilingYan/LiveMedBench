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

// Load leaderboard data and render table
async function loadLeaderboardData() {
    try {
        const response = await fetch('data/leaderboard.json');
        const data = await response.json();
        const tbody = document.getElementById('leaderboard-body');
        
        if (!tbody) return;
        
        // Clear existing rows
        tbody.innerHTML = '';
        
        // Render each model
        data.models.forEach(model => {
            const row = document.createElement('tr');
            row.setAttribute('data-type', model.type.toLowerCase().replace(/\s+/g, '-'));
            
            // Highlight top model
            if (model.rank === 1) {
                row.classList.add('top-model');
            }
            
            row.innerHTML = `
                <td>${model.rank}</td>
                <td><strong>${model.name}</strong></td>
                <td>${model.type}</td>
                <td><strong>${model.score_percent.toFixed(2)}</strong></td>
            `;
            
            tbody.appendChild(row);
        });
        
        // Update last updated date
        const lastUpdatedEl = document.getElementById('last-updated');
        if (lastUpdatedEl && data.last_updated) {
            lastUpdatedEl.textContent = data.last_updated;
        }
        
        // Setup filters after data is loaded
        setupFilters();
    } catch (error) {
        console.error('Failed to load leaderboard data:', error);
        tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-secondary);">Failed to load leaderboard data</td></tr>';
    }
}

// Leaderboard Filter Functionality
function setupFilters() {
    const filterButtons = document.querySelectorAll('.filter-btn');
    const leaderboardRows = document.querySelectorAll('#leaderboard-body tr');

    filterButtons.forEach(button => {
        button.addEventListener('click', () => {
            // Remove active class from all buttons
            filterButtons.forEach(btn => btn.classList.remove('active'));
            // Add active class to clicked button
            button.classList.add('active');
            
            const filter = button.getAttribute('data-filter');
            
            leaderboardRows.forEach(row => {
                const rowType = row.getAttribute('data-type') || '';
                
                if (filter === 'all') {
                    row.style.display = '';
                } else if (filter === 'proprietary' && rowType.includes('proprietary')) {
                    row.style.display = '';
                } else if (filter === 'opensource' && rowType.includes('open-source')) {
                    row.style.display = '';
                } else if (filter === 'medical' && rowType.includes('medical')) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        });
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

// Call on page load
loadLeaderboardData();

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
