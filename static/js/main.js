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
            console.log('Selected files:', fileInput.files);
            Array.from(fileInput.files).forEach(file => {
                formData.append('files', file);
                console.log('Appending file:', file.name);
            });

            // Add link if present
            const linkInput = document.getElementById('link');
            if (linkInput.value) {
                formData.append('link', linkInput.value);
                console.log('Appending link:', linkInput.value);
            }

            const progressBar = document.getElementById('uploadProgress');
            const progressBarInner = progressBar.querySelector('.progress-bar');

            try {
                progressBar.style.display = 'block';
                progressBarInner.style.width = '0%';

                console.log('Sending upload request...');
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });

                progressBarInner.style.width = '100%';
                const result = await response.json();
                console.log('Upload response:', result);

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

    // Study plan form submission
    const studyPlanForm = document.getElementById('study-plan-form');
    if (studyPlanForm) {
        studyPlanForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(studyPlanForm);

            try {
                console.log('Sending study plan request...');
                const response = await fetch('/study-plan', {  // Changed from /study-plan/new to /study-plan
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();
                console.log('Study plan response:', result);

                if (result.success) {
                    window.location.reload();
                } else {
                    alert('Failed to create study plan: ' + (result.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('Error:', error);
                alert('Failed to create study plan. Please try again.');
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
                console.log('Sending chat message:', message);
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ message })
                });
                const result = await response.json();
                console.log('Chat response:', result);

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