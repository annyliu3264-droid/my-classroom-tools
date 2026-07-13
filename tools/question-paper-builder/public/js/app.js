// 全域 Toast 通知函數
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    
    if (type === 'error') {
        toast.classList.add('toast-error');
    } else {
        toast.classList.remove('toast-error');
    }
    
    toast.classList.remove('hidden');
    
    // 3秒後消失
    setTimeout(() => {
        toast.classList.add('hidden');
    }, 3000);
}

// 全域空 DOMContentLoaded 監聽，留作擴充用
document.addEventListener('DOMContentLoaded', () => {
    // 預留做首頁載入初始化
});
