/**
 * YT Quid - Daily Content Quota & Native Desktop Reminder Engine
 * Periodically polls posting progress and dispatches native OS notifications.
 */

(function () {
    'use strict';

    const CHECK_INTERVAL_MS = 10 * 60 * 1000; // Check every 10 minutes
    const API_ENDPOINT = '/api/daily-posting-status/';

    /**
     * Request notification permission from browser/Electron if needed
     */
    function requestNotificationPermission() {
        if (!('Notification' in window)) return Promise.resolve(false);
        if (Notification.permission === 'granted') return Promise.resolve(true);
        if (Notification.permission !== 'denied') {
            return Notification.requestPermission().then(p => p === 'granted');
        }
        return Promise.resolve(false);
    }

    /**
     * Send native OS desktop notification
     */
    function sendDesktopNotification(title, body, tag) {
        if (!('Notification' in window) || Notification.permission !== 'granted') return;

        try {
            const notif = new Notification(title, {
                body: body,
                tag: tag || 'ytquid-reminder',
                renotify: true,
                silent: false
            });

            notif.onclick = function () {
                window.focus();
                this.close();
            };
        } catch (err) {
            console.warn('[YT Quid Reminders] Failed to dispatch notification:', err);
        }
    }

    /**
     * Evaluate posting status and trigger reminder if conditions are met
     */
    function evaluateAndRemind() {
        fetch(API_ENDPOINT)
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then(data => {
                if (!data || !data.reminders_enabled) return;

                const now = new Date();
                const currentHour = now.getHours();
                const todayKey = now.toISOString().slice(0, 10);

                const startHour = data.reminder_start_hour !== undefined ? data.reminder_start_hour : 9;
                const endHour = data.reminder_end_hour !== undefined ? data.reminder_end_hour : 21;
                const freqHours = data.reminder_frequency_hours || 3;
                const freqMs = freqHours * 60 * 60 * 1000;

                // 1. Goal Achieved Celebration
                if (data.is_goal_met) {
                    const lastCelebrated = localStorage.getItem('ytquid_goal_celebrated_date');
                    if (lastCelebrated !== todayKey) {
                        sendDesktopNotification(
                            '🏆 Daily Goal Achieved! (YT Quid)',
                            `Awesome! You've published ${data.today_count}/${data.target} contents today (${data.progress_pct}%). Streak: 🔥 ${data.current_streak} days!`,
                            'ytquid-celebration'
                        );
                        localStorage.setItem('ytquid_goal_celebrated_date', todayKey);
                    }
                    return;
                }

                // 2. Active Hours Check
                if (currentHour < startHour || currentHour >= endHour) {
                    return; // Outside user's preferred reminder hours
                }

                // 3. Frequency & Spam Throttling Check
                const lastReminderTs = parseInt(localStorage.getItem('ytquid_last_reminder_ts') || '0', 10);
                const timeSinceLastReminder = Date.now() - lastReminderTs;

                if (timeSinceLastReminder < freqMs) {
                    return; // Too soon since last reminder
                }

                // 4. Construct Contextual Motivational Message
                let message = '';
                if (data.today_count === 0) {
                    message = `☀️ Time to create! Today's target: ${data.target} contents. 0 uploaded so far. Keep your streak alive!`;
                } else if (data.progress_pct >= 70) {
                    message = `⚡ Almost there! You've posted ${data.today_count}/${data.target} contents today. Just ${data.remaining} more to reach your goal!`;
                } else {
                    message = `🎯 Daily Goal Progress: ${data.today_count}/${data.target} contents (${data.progress_pct}%). ${data.remaining} remaining today.`;
                }

                sendDesktopNotification(
                    'YT Quid • Daily Content Reminder',
                    message,
                    'ytquid-quota-reminder'
                );

                localStorage.setItem('ytquid_last_reminder_ts', Date.now().toString());
            })
            .catch(err => {
                // Silently ignore network or offline issues
                console.debug('[YT Quid Reminders] API check notice:', err.message);
            });
    }

    // Initialize when DOM is ready
    document.addEventListener('DOMContentLoaded', () => {
        // Request notification permission smoothly
        if ('Notification' in window && Notification.permission === 'default') {
            // Can request on first user interaction or automatically
            requestNotificationPermission();
        }

        // Initial check after 3 seconds
        setTimeout(evaluateAndRemind, 3000);

        // Recurring background timer
        setInterval(evaluateAndRemind, CHECK_INTERVAL_MS);
    });

    // Expose utility to window for manual testing or modal interaction
    window.YTQuidReminders = {
        checkNow: evaluateAndRemind,
        requestPermission: requestNotificationPermission
    };
})();
