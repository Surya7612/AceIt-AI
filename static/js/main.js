document.addEventListener('DOMContentLoaded', () => {
    feather.replace();

    // File upload handling
    const uploadForm = document.getElementById('uploadForm');
    if (uploadForm) {
        uploadForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData();

            // Add files
            const fileInput = document.getElementById('files');
            Array.from(fileInput.files).forEach(file => {
                formData.append('files', file);
            });

            // Add link if present
            const linkInput = document.getElementById('link');
            if (linkInput.value) {
                formData.append('link', linkInput.value);
            }

            const progressBar = document.getElementById('uploadProgress');
            const progressBarInner = progressBar.querySelector('.progress-bar');

            try {
                progressBar.style.display = 'block';
                progressBarInner.style.width = '0%';

                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });

                progressBarInner.style.width = '100%';
                const result = await response.json();

                if (result.success) {
                    alert('Files uploaded successfully!');
                    location.reload();
                } else {
                    alert('Upload failed: ' + result.error);
                }
            } catch (error) {
                console.error('Upload error:', error);
                alert('Upload failed. Please try again.');
            } finally {
                progressBar.style.display = 'none';
            }
        });
    }

    // Study plan generation
    const studyPlanForm = document.getElementById('study-plan-form');
    if (studyPlanForm) {
        studyPlanForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const topic = document.getElementById('topic').value;
            const duration = document.getElementById('duration').value;
            const goals = document.getElementById('goals').value;

            if (!topic || !duration || !goals) {
                alert('Please fill in all fields');
                return;
            }

            try {
                const response = await fetch('/study-plan/new', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ topic, duration, goals })
                });
                const result = await response.json();

                if (result.success) {
                    document.getElementById('generated-plan').style.display = 'block';
                    const plan = JSON.parse(result.plan);
                    let html = '<div class="study-plan-content">';
                    html += `<h6 class="mb-3">Total Duration: ${plan.total_duration}</h6>`;
                    html += '<h6 class="mb-2">Learning Goals:</h6>';
                    html += '<ul class="mb-3">';
                    plan.learning_goals.forEach(goal => {
                        html += `<li>${goal}</li>`;
                    });
                    html += '</ul>';
                    html += '<h6 class="mb-2">Study Sections:</h6>';
                    plan.sections.forEach(section => {
                        html += `<div class="card mb-3">
                            <div class="card-header">
                                <h6 class="mb-0">${section.title} (${section.duration})</h6>
                            </div>
                            <div class="card-body">
                                <ul class="mb-0">`;
                        section.tasks.forEach(task => {
                            html += `<li>${task}</li>`;
                        });
                        html += `</ul>
                            </div>
                        </div>`;
                    });
                    html += '</div>';
                    document.querySelector('.plan-content').innerHTML = html;
                } else {
                    alert('Failed to generate study plan: ' + result.error);
                }
            } catch (error) {
                console.error('Plan generation error:', error);
                alert('Failed to generate study plan. Please try again.');
            }
        });
    }

    // Chat functionality
    const chatForm = document.getElementById('chat-form');
    const chatMessages = document.getElementById('chat-messages');
    if (chatForm && chatMessages) {
        chatForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const input = document.getElementById('message-input');
            const message = input.value.trim();

            if (!message) return;

            // Add user message
            addMessage('user', message);
            input.value = '';

            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ message })
                });
                const result = await response.json();

                // Add AI response
                addMessage('assistant', result.response);
            } catch (error) {
                console.error('Chat error:', error);
                addMessage('assistant', 'Sorry, I encountered an error. Please try again.');
            }
        });
    }
});

function addMessage(type, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${type}`;
    messageDiv.textContent = content;

    const chatMessages = document.getElementById('chat-messages');
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}