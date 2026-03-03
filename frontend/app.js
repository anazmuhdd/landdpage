// Configuration
const API_BASE_URL = window.location.hostname === 'localhost' 
    ? 'http://localhost:10000' 
    : ''; // Will use same origin when deployed

// State Management
const state = {
    questions: [],
    currentQuestionIndex: 0,
    responses: {},
    conversationHistory: [], // Stores {question, answer} for LLM context
    isProcessing: false,
    currentFollowUpChain: [], // Track follow-up questions
    isInFollowUpMode: false
};

// DOM Elements
const elements = {
    chatContainer: document.getElementById('chatContainer'),
    userInput: document.getElementById('userInput'),
    sendBtn: document.getElementById('sendBtn'),
    ratingButtons: document.getElementById('ratingButtons'),
    skipBtn: document.getElementById('skipBtn'),
    typingIndicator: document.getElementById('typingIndicator'),
    progressBar: document.getElementById('progressBar'),
    progressText: document.getElementById('progressText'),
    completionScreen: document.getElementById('completionScreen'),
    inputContainer: document.getElementById('inputContainer')
};

// Initialize
async function init() {
    try {
        const response = await fetch(`${API_BASE_URL}/questions`);
        const data = await response.json();
        state.questions = data.questions;
        
        // Add start button
        addBotMessage("Ready to begin? Click the button below to start the survey.", [
            { text: "Start Survey", action: startSurvey, primary: true }
        ]);
        
        updateProgress();
    } catch (error) {
        console.error('Failed to load questions:', error);
        addBotMessage("Sorry, I couldn't load the survey questions. Please refresh the page to try again.");
    }
}

function startSurvey() {
    // Remove the start button message
    const startMsg = elements.chatContainer.lastElementChild;
    if (startMsg) startMsg.remove();
    
    // Show first question
    showQuestion(0);
}

function updateProgress() {
    const total = state.questions.length;
    const current = state.currentQuestionIndex + 1;
    const percent = (state.currentQuestionIndex / total) * 100;
    
    elements.progressBar.style.width = `${percent}%`;
    elements.progressText.textContent = `Question ${Math.min(current, total)} of ${total}`;
}

function showQuestion(index) {
    if (index >= state.questions.length) {
        submitSurvey();
        return;
    }
    
    const question = state.questions[index];
    state.currentQuestionIndex = index;
    state.isInFollowUpMode = false;
    state.currentFollowUpChain = [];
    
    updateProgress();
    
    // Show typing indicator
    showTyping();
    
    setTimeout(() => {
        hideTyping();
        
        let questionText = question.question;
        if (question.description) {
            questionText += `\n\n${question.description}`;
        }
        
        addBotMessage(questionText);
        showInputForQuestion(question);
        
        scrollToBottom();
    }, 600);
}

function showInputForQuestion(question) {
    // Hide all inputs first
    elements.userInput.style.display = 'none';
    elements.ratingButtons.style.display = 'none';
    elements.sendBtn.style.display = 'none';
    elements.skipBtn.style.display = 'none';
    
    elements.userInput.value = '';
    elements.userInput.disabled = false;
    
    // Show appropriate input based on type
    if (question.type === 'rating') {
        elements.ratingButtons.style.display = 'flex';
        setupRatingButtons();
    } else {
        elements.userInput.style.display = 'block';
        elements.sendBtn.style.display = 'flex';
        
        if (question.placeholder) {
            elements.userInput.placeholder = question.placeholder;
        }
        
        // Auto-resize textarea
        elements.userInput.addEventListener('input', autoResize);
        
        // Show skip button for optional questions
        if (!question.required) {
            elements.skipBtn.style.display = 'block';
        }
        
        // Focus input
        setTimeout(() => elements.userInput.focus(), 100);
    }
}

function setupRatingButtons() {
    const buttons = elements.ratingButtons.querySelectorAll('.rating-btn');
    buttons.forEach(btn => {
        btn.classList.remove('selected');
        btn.onclick = () => {
            buttons.forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
            handleRatingSelection(btn.dataset.value);
        };
    });
}

function autoResize() {
    this.style.height = 'auto';
    this.style.height = this.scrollHeight + 'px';
}

function handleRatingSelection(value) {
    if (state.isProcessing) return;
    
    const question = state.questions[state.currentQuestionIndex];
    processAnswer(value, question);
}

async function processAnswer(answer, question = null) {
    if (state.isProcessing) return;
    
    state.isProcessing = true;
    question = question || state.questions[state.currentQuestionIndex];
    
    // Hide inputs
    elements.ratingButtons.style.display = 'none';
    elements.userInput.style.display = 'none';
    elements.sendBtn.style.display = 'none';
    elements.skipBtn.style.display = 'none';
    
    // Add user message
    addUserMessage(answer);
    
    // Show typing
    showTyping();
    
    try {
        // Prepare context from conversation history
        const previousQA = state.isInFollowUpMode 
            ? [...state.conversationHistory, ...state.currentFollowUpChain.map((fq, i) => ({
                question: fq.question,
                answer: fq.answer
              }))]
            : state.conversationHistory;
        
        // Call validation API
        const response = await fetch(`${API_BASE_URL}/validate-answer`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: question.question,
                answer: answer,
                question_type: question.type,
                previous_qa: previousQA,
                is_follow_up: state.isInFollowUpMode
            })
        });
        
        const validation = await response.json();
        
        hideTyping();
        
        if (validation.follow_up_needed && validation.follow_up_question) {
            // Follow-up required - SELF DRIVEN LOOP
            state.isInFollowUpMode = true;
            state.currentFollowUpChain.push({
                question: question.question,
                answer: answer
            });
            
            // Show follow-up question
            setTimeout(() => {
                addBotMessage(validation.follow_up_question, [], true);
                
                // Show text input for follow-up
                elements.userInput.style.display = 'block';
                elements.userInput.placeholder = "Please provide more details...";
                elements.sendBtn.style.display = 'flex';
                elements.userInput.value = '';
                elements.userInput.disabled = false;
                elements.userInput.focus();
                
                state.isProcessing = false;
                scrollToBottom();
            }, 400);
            
        } else {
            // Answer is valid, no follow-up needed
            // Store the response (combine original + follow-ups if any)
            let finalAnswer = answer;
            if (state.currentFollowUpChain.length > 0) {
                const chainText = state.currentFollowUpChain.map(fq => 
                    `Q: ${fq.question}\nA: ${fq.answer}`
                ).join('\n\n');
                finalAnswer = `${chainText}\n\nFollow-up: ${answer}`;
            }
            
            state.responses[question.id] = finalAnswer;
            
            // Add to conversation history for next question context
            state.conversationHistory.push({
                question: question.question,
                answer: finalAnswer
            });
            
            // Show feedback if provided
            if (validation.feedback || validation.message) {
                addValidationFeedback(validation.feedback || validation.message);
            }
            
            // Move to next question
            setTimeout(() => {
                state.isProcessing = false;
                showQuestion(state.currentQuestionIndex + 1);
            }, 800);
        }
        
    } catch (error) {
        hideTyping();
        console.error('Validation error:', error);
        
        // On error, accept answer and move on
        state.responses[question.id] = answer;
        state.conversationHistory.push({
            question: question.question,
            answer: answer
        });
        
        addBotMessage("Thank you! Let's move to the next question.");
        
        setTimeout(() => {
            state.isProcessing = false;
            showQuestion(state.currentQuestionIndex + 1);
        }, 1000);
    }
}

function addBotMessage(text, actions = [], isFollowUp = false) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message bot-message ${isFollowUp ? 'follow-up' : ''}`;
    
    const content = document.createElement('div');
    content.className = 'message-content';
    
    // Handle newlines
    const lines = text.split('\n');
    lines.forEach((line, i) => {
        const p = document.createElement('p');
        p.textContent = line;
        content.appendChild(p);
    });
    
    // Add action buttons if provided
    if (actions.length > 0) {
        const btnContainer = document.createElement('div');
        btnContainer.style.marginTop = '12px';
        btnContainer.style.display = 'flex';
        btnContainer.style.gap = '8px';
        
        actions.forEach(action => {
            const btn = document.createElement('button');
            btn.textContent = action.text;
            btn.style.padding = '12px 24px';
            btn.style.borderRadius = '8px';
            btn.style.border = 'none';
            btn.style.cursor = 'pointer';
            btn.style.fontWeight = '600';
            
            if (action.primary) {
                btn.style.background = 'linear-gradient(135deg, #6366f1, #ec4899)';
                btn.style.color = 'white';
            } else {
                btn.style.background = '#f1f5f9';
                btn.style.color = '#475569';
            }
            
            btn.onclick = action.action;
            btnContainer.appendChild(btn);
        });
        
        content.appendChild(btnContainer);
    }
    
    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.textContent = isFollowUp ? '❓' : '🤖';
    
    messageDiv.appendChild(avatar);
    messageDiv.appendChild(content);
    
    elements.chatContainer.appendChild(messageDiv);
    scrollToBottom();
}

function addUserMessage(text) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message user-message';
    
    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.textContent = '👤';
    
    const content = document.createElement('div');
    content.className = 'message-content';
    const p = document.createElement('p');
    p.textContent = text;
    content.appendChild(p);
    
    messageDiv.appendChild(avatar);
    messageDiv.appendChild(content);
    
    elements.chatContainer.appendChild(messageDiv);
    scrollToBottom();
}

function addValidationFeedback(text) {
    const feedback = document.createElement('div');
    feedback.className = 'validation-feedback';
    feedback.textContent = `✓ ${text}`;
    elements.chatContainer.appendChild(feedback);
    scrollToBottom();
}

function showTyping() {
    elements.typingIndicator.style.display = 'flex';
    scrollToBottom();
}

function hideTyping() {
    elements.typingIndicator.style.display = 'none';
}

function scrollToBottom() {
    elements.chatContainer.scrollTop = elements.chatContainer.scrollHeight;
}

// Event Listeners
elements.sendBtn.addEventListener('click', () => {
    const answer = elements.userInput.value.trim();
    if (answer) {
        processAnswer(answer);
    }
});

elements.userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        const answer = elements.userInput.value.trim();
        if (answer) {
            processAnswer(answer);
        }
    }
});

elements.skipBtn.addEventListener('click', () => {
    const question = state.questions[state.currentQuestionIndex];
    processAnswer('Skipped (Optional)', question);
});

// Initialize app
init();