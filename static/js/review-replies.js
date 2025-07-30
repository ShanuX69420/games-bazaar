// Review Reply Functionality
document.addEventListener('DOMContentLoaded', function() {
    // Show reply form
    document.addEventListener('click', function(e) {
        if (e.target.matches('.show-reply-form-btn')) {
            e.preventDefault();
            const reviewId = e.target.dataset.reviewId;
            const replyForm = document.querySelector(`.reply-form[data-review-id="${reviewId}"]`);
            const button = e.target;
            
            button.style.display = 'none';
            replyForm.style.display = 'block';
            replyForm.querySelector('textarea').focus();
        }
        
        // Cancel reply
        if (e.target.matches('.cancel-reply-btn')) {
            e.preventDefault();
            const form = e.target.closest('.reply-form');
            const reviewId = form.dataset.reviewId;
            const button = document.querySelector(`.show-reply-form-btn[data-review-id="${reviewId}"]`);
            
            form.style.display = 'none';
            form.reset();
            if (button) button.style.display = 'inline-block';
        }
        
        // Edit reply
        if (e.target.matches('.edit-reply-btn')) {
            e.preventDefault();
            const replyId = e.target.dataset.replyId;
            
            // Get current reply text
            fetch(`/review-reply/${replyId}/edit/`)
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        const replyDiv = e.target.closest('.review-reply');
                        const originalContent = replyDiv.querySelector('.reply-content').innerHTML;
                        
                        replyDiv.querySelector('.reply-content').innerHTML = `
                            <form class="edit-reply-form" data-reply-id="${replyId}">
                                <textarea class="form-control mb-2" rows="3" maxlength="1000" required>${data.reply_text}</textarea>
                                <div class="d-flex gap-2">
                                    <button type="submit" class="btn btn-primary btn-sm">Update Reply</button>
                                    <button type="button" class="btn btn-secondary btn-sm cancel-edit-reply-btn" data-original-content="${encodeURIComponent(originalContent)}">Cancel</button>
                                </div>
                            </form>
                        `;
                        
                        replyDiv.querySelector('textarea').focus();
                    }
                })
                .catch(error => console.error('Error loading reply data:', error));
        }
        
        // Cancel edit reply
        if (e.target.matches('.cancel-edit-reply-btn')) {
            e.preventDefault();
            const replyDiv = e.target.closest('.review-reply');
            const originalContent = decodeURIComponent(e.target.dataset.originalContent);
            
            replyDiv.querySelector('.reply-content').innerHTML = originalContent;
        }
        
        // Delete reply
        if (e.target.matches('.delete-reply-btn')) {
            e.preventDefault();
            if (confirm('Are you sure you want to delete this reply? This action cannot be undone.')) {
                const replyId = e.target.dataset.replyId;
                
                fetch(`/review-reply/${replyId}/delete/`, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        const replyDiv = e.target.closest('.review-reply');
                        const reviewCard = replyDiv.closest('.review-card');
                        
                        replyDiv.remove();
                        
                        // Show reply button again if it exists
                        const replyFormContainer = reviewCard.querySelector('.reply-form-container');
                        if (replyFormContainer) {
                            replyFormContainer.style.display = 'block';
                        }
                        
                        alert(data.message);
                    } else {
                        alert(data.message || 'Error deleting reply');
                    }
                })
                .catch(error => {
                    console.error('Error deleting reply:', error);
                    alert('Error deleting reply');
                });
            }
        }
    });
    
    // Handle reply form submissions
    document.addEventListener('submit', function(e) {
        if (e.target.matches('.reply-form')) {
            e.preventDefault();
            const form = e.target;
            const reviewId = form.dataset.reviewId;
            const formData = new FormData(form);
            
            const submitBtn = form.querySelector('button[type="submit"]');
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Posting...';
            
            fetch(`/review/${reviewId}/reply/`, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': formData.get('csrfmiddlewaretoken')
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    // Add the reply HTML after the review comment
                    const reviewCard = form.closest('.review-card');
                    const reviewContent = reviewCard.querySelector('.review-content');
                    const replyFormContainer = reviewCard.querySelector('.reply-form-container');
                    
                    reviewContent.insertAdjacentHTML('beforeend', data.reply_html);
                    replyFormContainer.remove();
                    
                    alert(data.message);
                } else {
                    alert(data.message || 'Error posting reply');
                }
            })
            .catch(error => {
                console.error('Error posting reply:', error);
                alert('Error posting reply');
            })
            .finally(() => {
                submitBtn.disabled = false;
                submitBtn.innerHTML = 'Post Reply';
            });
        }
        
        // Handle edit reply form submissions
        if (e.target.matches('.edit-reply-form')) {
            e.preventDefault();
            const form = e.target;
            const replyId = form.dataset.replyId;
            const formData = new FormData(form);
            
            const submitBtn = form.querySelector('button[type="submit"]');
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Updating...';
            
            fetch(`/review-reply/${replyId}/edit/`, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    const replyDiv = form.closest('.review-reply');
                    replyDiv.outerHTML = data.reply_html;
                    alert(data.message);
                } else {
                    alert(data.message || 'Error updating reply');
                }
            })
            .catch(error => {
                console.error('Error updating reply:', error);
                alert('Error updating reply');
            })
            .finally(() => {
                submitBtn.disabled = false;
                submitBtn.innerHTML = 'Update Reply';
            });
        }
    });
});