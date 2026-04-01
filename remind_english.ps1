# remind_english.ps1 — Notification Windows pour réviser l'anglais
param(
    [string]$Message = "Time to practice your English! 🎙️",
    [string]$Title = "English Learning Reminder"
)

# Charger l'assembly Windows Forms pour les notifications
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# Créer l'icône dans la barre des tâches
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Information
$notify.Visible = $true
$notify.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Info
$notify.BalloonTipTitle = $Title
$notify.BalloonTipText = $Message

# Afficher la notification pendant 10 secondes
$notify.ShowBalloonTip(10000)

# Garder le script en vie le temps que la notification s'affiche
Start-Sleep -Seconds 5

# Nettoyer
$notify.Dispose()
