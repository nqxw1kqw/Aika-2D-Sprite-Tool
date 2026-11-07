// Unity C# Sprite Sheet Auto-Runner for `jirai_neko`
using System.Collections.Generic;
using UnityEngine;

[RequireComponent(typeof(SpriteRenderer))]
public class SpriteAutoRunner : MonoBehaviour
{
    public Texture2D atlasTexture;
    public int cellWidth = 256;
    public int cellHeight = 256;
    public string currentState = "walk";
    public float moveSpeed = 3.5f;

    private struct AnimRow
    {
        public int rowIndex;
        public int frameCount;
        public float fps;
        public AnimRow(int r, int c, float f) { rowIndex = r; frameCount = c; fps = f; }
    }

    private readonly Dictionary<string, AnimRow> _rows = new Dictionary<string, AnimRow>
    {
        { "idle", new AnimRow(0, 4, 5.0f) },
        { "walk", new AnimRow(1, 6, 8.0f) },
    };

    private SpriteRenderer _sr;
    private Dictionary<string, Sprite[]> _sprites = new Dictionary<string, Sprite[]>();
    private float _timer;
    private int _frameIdx;

    void Awake()
    {
        _sr = GetComponent<SpriteRenderer>();
        if (atlasTexture == null) return;
        atlasTexture.filterMode = FilterMode.Point; // Crisp Pixel Art
        int totalRows = _rows.Count;
        foreach (var kv in _rows)
        {
            var row = kv.Value;
            var arr = new Sprite[row.frameCount];
            int yTop = atlasTexture.height - (row.rowIndex + 1) * cellHeight;
            for (int i = 0; i < row.frameCount; i++)
            {
                Rect rect = new Rect(i * cellWidth, yTop, cellWidth, cellHeight);
                arr[i] = Sprite.Create(atlasTexture, rect, new Vector2(0.5f, 0f), 100f);
            }
            _sprites[kv.Key] = arr;
        }
    }

    void Update()
    {
        if (!_sprites.ContainsKey(currentState)) return;
        var row = _rows[currentState];
        _timer += Time.deltaTime;
        if (_timer >= 1f / row.fps)
        {
            _timer = 0f;
            _frameIdx = (_frameIdx + 1) % row.frameCount;
            _sr.sprite = _sprites[currentState][_frameIdx];
        }

        float h = Input.GetAxisRaw("Horizontal");
        if (Mathf.Abs(h) > 0.01f)
        {
            _sr.flipX = h < 0;
            transform.Translate(Vector3.right * (h * moveSpeed * Time.deltaTime));
        }
    }
}
