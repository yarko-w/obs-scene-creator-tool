using System.ComponentModel;
using System.Runtime.CompilerServices;

namespace OBSSceneGenerator.Models;

/// <summary>
/// Represents one editable row in the preset table.
/// Position is stored as string for clean TextBox binding and validation.
/// </summary>
public class PresetRow : INotifyPropertyChanged
{
    private string _name = "";
    private string _position = "1";
    private int _rowNumber = 1;
    private bool _hasPositionError;

    public string Name
    {
        get => _name;
        set { _name = value; OnPropertyChanged(); }
    }

    public string Position
    {
        get => _position;
        set
        {
            _position = value;
            OnPropertyChanged();
            HasPositionError = !IsValidPosition(value);
        }
    }

    public int RowNumber
    {
        get => _rowNumber;
        set { _rowNumber = value; OnPropertyChanged(); }
    }

    /// <summary>True when Position text is not a valid PTZ position (0–89 or 100–254).</summary>
    public bool HasPositionError
    {
        get => _hasPositionError;
        set { _hasPositionError = value; OnPropertyChanged(); }
    }

    /// <summary>Parses Position to int if valid, returns null otherwise.</summary>
    public int? ParsedPosition => int.TryParse(_position, out var n) && IsValidPosition(n) ? n : null;

    public static bool IsValidPosition(string text)
        => int.TryParse(text, out var n) && IsValidPosition(n);

    public static bool IsValidPosition(int n)
        => (n >= 0 && n <= 89) || (n >= 100 && n <= 254);

    public event PropertyChangedEventHandler? PropertyChanged;

    private void OnPropertyChanged([CallerMemberName] string? name = null)
        => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
}
