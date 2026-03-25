using System.Collections.ObjectModel;
using System.IO;
using System.Net;
using System.Text.Json;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using Microsoft.Win32;
using OBSSceneGenerator.Models;
using OBSSceneGenerator.Services;

namespace OBSSceneGenerator;

public partial class MainWindow : Window
{
    // Bound to the ItemsControl in XAML via DataContext = this
    public ObservableCollection<PresetRow> Presets { get; } = [];

    public MainWindow()
    {
        InitializeComponent();
        DataContext = this;
        RebuildPresetRows(3);
        UpdateUrlPreview();
    }

    // ── Brushes for validation feedback ─────────────────────────────────
    private static readonly Brush ErrorBgBrush     = (Brush)Application.Current.Resources["ErrorBg"];
    private static readonly Brush NormalInputBrush = (Brush)Application.Current.Resources["InputBg"];

    // ── URL preview + IP validation ──────────────────────────────────────

    private void CameraIpBox_TextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e)
    {
        UpdateUrlPreview();
        ValidateIpField();
    }

    private void UpdateUrlPreview()
    {
        if (UrlPreviewText == null) return;
        var ip = CameraIpBox?.Text.Trim();
        if (string.IsNullOrEmpty(ip)) ip = "<camera-ip>";
        UrlPreviewText.Text = $"http://{ip}/cgi-bin/ptzctrl.cgi?ptzcmd&poscall&1";
    }

    private void ValidateIpField()
    {
        if (CameraIpBox == null) return;
        var text = CameraIpBox.Text.Trim();
        bool valid = string.IsNullOrEmpty(text) || IsValidIpAddress(text);
        CameraIpBox.Background = valid ? NormalInputBrush : ErrorBgBrush;
    }

    private static bool IsValidIpAddress(string text)
        => IPAddress.TryParse(text, out var addr) && addr.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork;

    // ── Numeric-only input filter (used by preset count and position fields)

    private void NumericOnly_PreviewTextInput(object sender, TextCompositionEventArgs e)
        => e.Handled = !e.Text.All(char.IsDigit);

    // ── Preset count spinner ──────────────────────────────────────────────

    private void PresetCountBox_TextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e)
    {
        if (!IsLoaded) return;
        var text = PresetCountBox.Text.Trim();
        bool valid = int.TryParse(text, out var count) && count >= 1 && count <= 20;
        PresetCountBox.Background = (string.IsNullOrEmpty(text) || !valid) ? ErrorBgBrush : NormalInputBrush;
        if (valid)
            RebuildPresetRows(count);
    }

    private void PresetCountUp_Click(object sender, RoutedEventArgs e)
    {
        var current = int.TryParse(PresetCountBox.Text, out var n) ? Math.Clamp(n, 1, 20) : 1;
        if (current < 20) PresetCountBox.Text = (current + 1).ToString();
    }

    private void PresetCountDown_Click(object sender, RoutedEventArgs e)
    {
        var current = int.TryParse(PresetCountBox.Text, out var n) ? Math.Clamp(n, 1, 20) : 2;
        if (current > 1) PresetCountBox.Text = (current - 1).ToString();
    }

    private void RebuildPresetRows(int count)
    {
        var existingNames     = Presets.Select(p => p.Name).ToList();
        var existingPositions = Presets.Select(p => p.Position).ToList();

        while (Presets.Count > count)
            Presets.RemoveAt(Presets.Count - 1);

        for (int i = Presets.Count; i < count; i++)
        {
            Presets.Add(new PresetRow
            {
                Name     = i < existingNames.Count     ? existingNames[i]     : $"Preset {i + 1}",
                Position = i < existingPositions.Count ? existingPositions[i] : (i + 1).ToString()
            });
        }

        UpdateRowNumbers();
    }

    // ── Optional scene checkboxes ─────────────────────────────────────────

    private void SceneOptionChanged(object sender, RoutedEventArgs e)
    {
        if (!IsLoaded) return;
        MediaRowGrid.Visibility = IncludeMediaCheck.IsChecked == true ? Visibility.Visible : Visibility.Collapsed;
        BlackRowGrid.Visibility = IncludeBlackCheck.IsChecked == true ? Visibility.Visible : Visibility.Collapsed;
        UpdateRowNumbers();
    }

    private void UpdateRowNumbers()
    {
        bool hasMedia = IncludeMediaCheck?.IsChecked == true;
        bool hasBlack = IncludeBlackCheck?.IsChecked == true;
        int offset = hasMedia ? 2 : 1;

        for (int i = 0; i < Presets.Count; i++)
            Presets[i].RowNumber = i + offset;

        if (BlackRowNumberText != null)
            BlackRowNumberText.Text = ((hasMedia ? 1 : 0) + Presets.Count + 1).ToString();
    }

    // ── Generate ──────────────────────────────────────────────────────────

    private async void GenerateButton_Click(object sender, RoutedEventArgs e)
    {
        var name = CollectionNameBox.Text.Trim();
        var ip   = CameraIpBox.Text.Trim();

        if (string.IsNullOrEmpty(name))  { ShowError("Missing Info", "Please enter a collection name."); return; }
        if (string.IsNullOrEmpty(ip))    { ShowError("Missing Info", "Please enter the camera IP address."); return; }
        if (!IsValidIpAddress(ip))       { ShowError("Invalid IP", "Please enter a valid IPv4 address (e.g. 192.168.1.100)."); return; }

        var presets       = new List<PresetConfig>();
        var seenNames     = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var seenPositions = new HashSet<int>();

        for (int i = 0; i < Presets.Count; i++)
        {
            var row = Presets[i];
            if (string.IsNullOrWhiteSpace(row.Name))
            { ShowError("Missing Info", $"Preset {i + 1}: scene name cannot be empty."); return; }

            if (!seenNames.Add(row.Name))
            { ShowError("Duplicate Name", $"Scene name \"{row.Name}\" is used more than once."); return; }

            var pos = row.ParsedPosition;
            if (pos == null)
            {
                ShowError("Invalid Position",
                    $"Preset {i + 1}: position must be 0–89 or 100–254.\n\n" +
                    $"Current value: \"{row.Position}\"");
                return;
            }

            if (!seenPositions.Add(pos.Value))
            {
                if (MessageBox.Show(this, $"Position {pos.Value} is used more than once.\n\nContinue anyway?",
                    "Duplicate Position", MessageBoxButton.YesNo, MessageBoxImage.Warning) != MessageBoxResult.Yes)
                    return;
            }

            presets.Add(new PresetConfig(row.Name, pos.Value));
        }

        string transition = StingerRadio.IsChecked == true ? "Stinger"
                          : FadeRadio.IsChecked    == true ? "Fade"
                          : "Cut";
        bool includeMedia = IncludeMediaCheck.IsChecked == true;
        bool includeBlack = IncludeBlackCheck.IsChecked == true;

        var collection = ObsJsonBuilder.Build(name, ip, presets, includeMedia, includeBlack, transition);

        var dialog = new SaveFileDialog
        {
            Title      = "Save OBS Scene Collection",
            DefaultExt = ".json",
            FileName   = $"{name}.json",
            Filter     = "OBS Scene Collection (*.json)|*.json|All Files (*.*)|*.*"
        };
        if (dialog.ShowDialog(this) != true) return;

        await File.WriteAllTextAsync(dialog.FileName,
            collection.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));

        if (transition == "Stinger")
        {
            GenerateButton.IsEnabled  = false;
            ProgressPanel.Visibility  = Visibility.Visible;
            DownloadProgressBar.Value = 0;
            ProgressLabel.Text        = "Downloading stinger file…";

            try
            {
                var progress = new Progress<int>(pct =>
                {
                    DownloadProgressBar.Value = pct;
                    if (pct >= 100) ProgressLabel.Text = $"Saved to {StingerDownloader.StingerFolder}";
                });
                await StingerDownloader.DownloadAsync(progress);
                await Task.Delay(1200);
            }
            catch (Exception ex)
            {
                ShowError("Download Failed",
                    $"Could not download the stinger file:\n\n{ex.Message}\n\n" +
                    $"You can download it manually and place it at:\n" +
                    $"{StingerDownloader.StingerFolder}\\{StingerDownloader.StingerFile}");
            }
            finally
            {
                ProgressPanel.Visibility = Visibility.Collapsed;
                GenerateButton.IsEnabled = true;
            }
        }

        var mediaLine   = includeMedia ? "  • Media\n" : "";
        var blackLine   = includeBlack ? "  • Black\n" : "";
        var presetLines = string.Concat(presets.Select(p => $"  • {p.Name} (PTZ pos {p.Position})\n"));

        MessageBox.Show(this,
            $"Scene collection saved!\n\n{dialog.FileName}\n\n" +
            $"Scenes created:\n{mediaLine}{presetLines}{blackLine}\n" +
            $"Transition: {transition}\n" +
            $"Video source: PTZ Camera (shared across all preset scenes)\n\n" +
            $"Import in OBS via:\nScene Collection → Import",
            "Success", MessageBoxButton.OK, MessageBoxImage.Information);
    }

    private void ShowError(string title, string message)
        => MessageBox.Show(this, message, title, MessageBoxButton.OK, MessageBoxImage.Error);
}
