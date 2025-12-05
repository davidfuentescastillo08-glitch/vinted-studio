document.addEventListener('DOMContentLoaded', () => {
    const fileInput = document.getElementById('file-input');

    // Stages
    const uploadStage = document.getElementById('upload-stage');
    const processingStage = document.getElementById('processing-stage');
    const resultStage = document.getElementById('result-stage');

    // Elements
    const imgBefore = document.getElementById('img-before');
    const imgAfter = document.getElementById('img-after');
    const downloadBtn = document.getElementById('download-btn');
    const resetBtn = document.getElementById('reset-btn');

    // Slider Elements
    const slider = document.getElementById('slider');
    const beforeWrapper = document.querySelector('.img-wrapper.before');
    const handle = document.querySelector('.handle');
    const container = document.getElementById('comparison-container');

    // Handle File Upload
    fileInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        // 1. Show local preview as "Before" immediately
        const reader = new FileReader();
        reader.onload = (e) => {
            imgBefore.src = e.target.result;
            // Need to wait for image load to set container height properly
            imgBefore.onload = () => {
                // Ensure container matches image aspect ratio
                // Actually, CSS relative positioning should handle it if 'after' img is main
                // But initially only 'before' is loaded.
            }
        };
        reader.readAsDataURL(file);

        // 2. Transition State
        showStage(processingStage);

        // 3. Upload and Process
        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/process', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (data.success) {
                // 4. Show Result
                imgAfter.src = data.image;

                // Adjust download link
                downloadBtn.href = data.image;

                // Wait for image to load to display safely
                imgAfter.onload = () => {
                    initSlider();
                    showStage(resultStage);
                };
            } else {
                alert('Error al procesar: ' + (data.error || 'Desconocido'));
                showStage(uploadStage);
            }

        } catch (err) {
            console.error(err);
            alert('Error de conexión.');
            showStage(uploadStage);
        }
    });

    // Reset Flow
    resetBtn.addEventListener('click', () => {
        fileInput.value = '';
        showStage(uploadStage);
    });

    // Slider Logic
    slider.addEventListener('input', (e) => {
        const value = e.target.value;
        updateSlider(value);
    });

    function updateSlider(percent) {
        // Move the split line
        beforeWrapper.style.width = percent + '%';
        handle.style.left = percent + '%';
    }

    function initSlider() {
        // Reset slider
        slider.value = 50;
        updateSlider(50);

        // Sync before image width to match the container width exactly
        // to prevent squishing as the wrapper shrinks.
        // We set the img width to the container's offsetWidth
        const width = container.offsetWidth;
        imgBefore.style.width = width + 'px';
        imgAfter.style.width = width + 'px'; // Ensure consistency
    }

    // Handle resizing
    window.addEventListener('resize', () => {
        if (resultStage.style.display !== 'none') {
            const width = container.offsetWidth;
            imgBefore.style.width = width + 'px';
            imgAfter.style.width = width + 'px';
        }
    });

    function showStage(stage) {
        document.querySelectorAll('.stage').forEach(el => el.classList.remove('active'));
        stage.classList.add('active');
    }
});
