const API_BASE = window.location.protocol === 'file:' ? 'http://127.0.0.1:5000' : '';

document.addEventListener('DOMContentLoaded', () => {
    // Stats Counter Animation
    const animateStats = async () => {
        try {
            const res = await fetch(`${API_BASE}/api/stats`);
            const data = await res.json();
            
            const statsConfig = [
                { id: 'stat-students', target: data.students || 0 },
                { id: 'stat-teachers', target: data.teachers || 0 },
                { id: 'stat-awards', target: data.awards || 0 },
                { id: 'stat-experience', target: data.experience || 0 }
            ];

            statsConfig.forEach(config => {
                const el = document.getElementById(config.id);
                if (!el) return;
                
                const target = config.target;
                let count = 0;
                const increment = Math.max(1, target / 100);
                
                const updateCount = () => {
                    if (count < target) {
                        count += increment;
                        el.innerText = Math.ceil(count);
                        setTimeout(updateCount, 20);
                    } else {
                        el.innerText = target;
                    }
                };
                updateCount();
            });
        } catch (err) {
            console.error('Error fetching stats:', err);
        }
    };

    // Intersection Observer for stats
    const statsSection = document.querySelector('.stats');
    if (statsSection) {
        const observer = new IntersectionObserver((entries) => {
            if (entries[0].isIntersecting) {
                animateStats();
                observer.unobserve(statsSection);
            }
        }, { threshold: 0.5 });
        observer.observe(statsSection);
    }

    // Fetch Announcements (Limited for Preview)
    const announcementGrid = document.querySelector('.announcement-grid');
    if (announcementGrid && (window.location.pathname.includes('index.html') || window.location.pathname === '/' || window.location.pathname.endsWith('/'))) {
        fetch(`${API_BASE}/api/announcements`)
            .then(res => {
                if (!res.ok) throw new Error('Network response was not ok');
                return res.json();
            })
            .then(data => {
                const previewData = data.slice(0, 3);
                if (previewData.length === 0) {
                    announcementGrid.innerHTML = '<p class="text-muted">لا توجد إعلانات حالياً</p>';
                    return;
                }
                announcementGrid.innerHTML = previewData.map(ann => {
                    const images = ann.image_url ? ann.image_url.split(',') : [];
                    return `
                    <div class="announcement-card">
                        <div class="ann-image">
                            ${images.length > 0 ? `<img src="${images[0]}" alt="${ann.title}">` : '<i class="fas fa-image fa-3x"></i>'}
                        </div>
                        <div class="ann-content">
                            <span class="ann-tag">${ann.type}</span>
                            <h3 class="ann-title">${ann.title}</h3>
                            <p class="ann-excerpt">${ann.content.substring(0, 100)}...</p>
                            <div class="ann-footer">
                                <span class="ann-date">${new Date(ann.created_at).toLocaleDateString('ar-MA')}</span>
                                <a href="details.html?type=announcement&id=${ann.id}" class="read-more">اقرأ المزيد <i class="fas fa-arrow-left"></i></a>
                            </div>
                        </div>
                    </div>
                `}).join('');
            })
            .catch(err => {
                console.error('Error fetching announcements:', err);
                announcementGrid.innerHTML = '<p class="text-danger">عذراً، حدث خطأ أثناء تحميل الإعلانات. يرجى تحديث الصفحة.</p>';
            });
    }

    // Generic Load Full Section (announcements.html, activities.html, gallery.html, student-space.html, about.html)
    const loadFullSection = async (sectionId, apiPath, templateFn) => {
        const container = document.getElementById(sectionId);
        if (!container) return;
        
        container.innerHTML = '<div class="loading" style="padding: 20px; text-align: center;"><i class="fas fa-spinner fa-spin"></i> جاري تحميل البيانات...</div>';
        
        try {
            const endpoints = [`${API_BASE}${apiPath}`, apiPath, `${API_BASE}${apiPath.replace('/api', '')}`].filter((v, i, a) => a.indexOf(v) === i);
            let response = null;
            let lastError = null;

            for (const url of endpoints) {
                try {
                    console.log(`Trying data endpoint: ${url}`);
                    const res = await fetch(url);
                    if (res.ok) {
                        response = res;
                        break;
                    }
                } catch (err) {
                    lastError = err;
                }
            }
            
            if (!response) {
                throw new Error(`تعذر الاتصال بقاعدة البيانات. (آخر خطأ: ${lastError?.message || '404'})`);
            }

            const data = await response.json();
            
            if (!data || data.length === 0) {
                container.innerHTML = '<div class="container text-center" style="padding: 40px;"><p class="text-muted">لا يوجد محتوى متوفر حالياً في هذا القسم.</p></div>';
                return;
            }
            container.innerHTML = data.map(templateFn).join('');
        } catch (err) {
            console.error(`Error loading ${sectionId} from ${apiPath}:`, err);
            container.innerHTML = `<div class="container text-center" style="padding: 40px; border: 1px dashed #feb2b2; border-radius: 12px; background: #fff5f5;"><p class="text-danger" style="font-weight: bold;">❌ ${err.message}</p><button onclick="window.location.reload()" class="btn" style="margin-top: 10px; background: var(--primary-dark); color: white;">إعادة المحاولة</button></div>`;
        }
    };

    // Announcements Page
    loadFullSection('full-announcements', '/api/announcements', ann => `
        <div class="announcement-card h-100">
            <div class="ann-content">
                <span class="ann-tag">${ann.type}</span>
                <h3 class="ann-title">${ann.title}</h3>
                <p>${ann.content.substring(0, 150)}...</p>
                <div class="ann-footer">
                    <span class="ann-date">${new Date(ann.created_at).toLocaleDateString('ar-MA')}</span>
                    <a href="details.html?type=announcement&id=${ann.id}" class="read-more">اقرأ المزيد <i class="fas fa-arrow-left"></i></a>
                </div>
            </div>
        </div>
    `);

    // Activities Page
    loadFullSection('full-activities', '/api/activities', act => {
        const images = act.image_url ? act.image_url.split(',') : [];
        return `
        <div class="activity-card">
            <div class="activity-img">
                ${images.length > 0 ? `<img src="${images[0]}" alt="${act.title}">` : '<i class="fas fa-calendar-alt fa-3x"></i>'}
            </div>
            <div class="activity-body">
                <h3>${act.title}</h3>
                <p>${act.content.substring(0, 120)}...</p>
                <a href="details.html?type=activity&id=${act.id}" class="btn">إقرأ المزيد</a>
            </div>
        </div>
    `});

    // Gallery Page
    loadFullSection('full-gallery', '/api/gallery', img => `
        <div class="gallery-item">
            <img src="${img.image_url}" alt="${img.title || ''}">
            <div class="gallery-overlay">
                <span>${img.title || ''}</span>
            </div>
        </div>
    `);

    // Student Space
    loadFullSection('full-student-space', '/api/resources', res => `
        <div class="course-card">
            <div class="course-icon"><i class="fas fa-file-pdf"></i></div>
            <h3>${res.title}</h3>
            <p>${res.category} - ${res.description || ''}</p>
            <a href="${res.link_url}" class="download-btn" target="_blank">تحميل المورد <i class="fas fa-download"></i></a>
        </div>
    `);

    // Staff List (about.html)
    loadFullSection('full-staff', '/api/staff', s => `
        <div class="staff-card">
            <div class="staff-avatar">
                ${s.image_url ? `<img src="${s.image_url}" alt="${s.name}" style="width:100%; height:100%; border-radius:50%; object-fit:cover;">` : '<i class="fas fa-user-tie"></i>'}
            </div>
            <div class="staff-name">${s.name}</div>
            <div class="staff-role">${s.role}</div>
        </div>
    `);
});
