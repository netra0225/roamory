package de.s42.swapmyaxe.config;

import de.s42.swapmyaxe.SwapMyAxe;
import me.shedaniel.clothconfig2.api.ConfigBuilder;
import me.shedaniel.clothconfig2.api.ConfigCategory;
import me.shedaniel.clothconfig2.api.ConfigEntryBuilder;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

public class ConfigScreen {

    public Screen buildScreen(Screen parent) {
        Config cfg = SwapMyAxe.CONFIG;

        ConfigBuilder builder = ConfigBuilder.create()
                .setParentScreen(parent)
                .setTitle(Component.literal("SwapMyAxe Config"))
                .setSavingRunnable(cfg::save);

        ConfigEntryBuilder entry = builder.entryBuilder();
        ConfigCategory general = builder.getOrCreateCategory(Component.literal("General"));

        general.addEntry(entry.startBooleanToggle(Component.literal("Enable Mod"), cfg.enabled)
                .setDefaultValue(true)
                .setTooltip(Component.literal("Toggle SwapMyAxe on / off"))
                .setSaveConsumer(v -> cfg.enabled = v)
                .build());

        general.addEntry(entry.startBooleanToggle(Component.literal("Double Hit"), cfg.doubleHit)
                .setDefaultValue(true)
                .setTooltip(Component.literal("Also swing / attack with the swapped slot immediately after the swap"))
                .setSaveConsumer(v -> cfg.doubleHit = v)
                .build());

        general.addEntry(entry.startBooleanToggle(Component.literal("Restore to Axe"), cfg.restoreToAxe)
                .setDefaultValue(false)
                .setTooltip(Component.literal("If true, switch back to the original axe slot after the swapped hit"))
                .setSaveConsumer(v -> cfg.restoreToAxe = v)
                .build());

        general.addEntry(entry.startIntSlider(Component.literal("Swap Delay (ticks)"), cfg.swapDelayTicks, 0, 20)
                .setDefaultValue(0)
                .setTooltip(Component.literal("Delay between original hit and swap hit (0 = instant)"))
                .setSaveConsumer(v -> cfg.swapDelayTicks = v)
                .build());

        ConfigCategory swapMode = builder.getOrCreateCategory(Component.literal("Swap Mode"));

        swapMode.addEntry(entry.startEnumSelector(Component.literal("Swap Mode"), Config.SwapMode.class, cfg.swapMode)
                .setDefaultValue(Config.SwapMode.SLOT)
                .setTooltip(
                        Component.literal("SLOT → swap to a specific hotbar slot"),
                        Component.literal("ITEM → swap to the first slot that holds the configured item")
                )
                .setSaveConsumer(v -> cfg.swapMode = v)
                .build());

        swapMode.addEntry(entry.startIntSlider(Component.literal("Target Hotbar Slot"), cfg.targetSlot, 0, 8)
                .setDefaultValue(1)
                .setTooltip(Component.literal("Hotbar slot index (0-8) used in SLOT mode"))
                .setSaveConsumer(v -> cfg.targetSlot = v)
                .build());

        swapMode.addEntry(entry.startStrField(Component.literal("Target Item ID"), cfg.targetItem)
                .setDefaultValue("minecraft:diamond_sword")
                .setTooltip(Component.literal("Registry id used in ITEM mode (e.g. minecraft:diamond_sword or minecraft:mace)"))
                .setSaveConsumer(v -> cfg.targetItem = v)
                .build());

        return builder.build();
    }
}
