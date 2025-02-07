// Initialize Feather icons
document.addEventListener('DOMContentLoaded', () => {
    feather.replace();
    
    // File upload handling
    const uploadForm = document.getElementById('uploadForm');
    if (uploadForm) {
        uploadForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(uploadForm);
            
            try {
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });
                const result = await response.json();
                
                if (result.success) {
                    alert('File uploaded successfully!');
                    location.reload();
                } else {
                    alert('Upload failed: ' + result.error);
                }
            } catch (error) {
                console.error('Upload error:', error);
                alert('Upload failed. Please try again.');
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

    // Study plan generation
    const generatePlanBtn = document.getElementById('generate-plan');
    if (generatePlanBtn) {
        generatePlanBtn.addEventListener('click', async () => {
            const topic = document.getElementById('topic').value;
            const duration = document.getElementById('duration').value;
            const goals = document.getElementById('goals').value;

            if (!topic || !duration || !goals) {
                alert('Please fill in all fields');
                return;
            }

            try {
                const response = await fetch('/generate-plan', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ topic, duration, goals })
                });
                const result = await response.json();
                
                document.getElementById('generated-plan').style.display = 'block';
                document.querySelector('.plan-content').innerHTML = result.plan;
            } catch (error) {
                console.error('Plan generation error:', error);
                alert('Failed to generate study plan. Please try again.');
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
